"""Periodic purge of data past its configured retention window, plus
compressing aged-out client minute data into hourly rows first.

Raw events and aggregates are purged on independent schedules
(RETENTION_DAYS_RAW_EVENTS vs. RETENTION_DAYS_AGGREGATES) since aggregates
are cheap to keep for long-term trend reporting while raw per-event detail
is comparatively expensive to retain.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.archive_run import ArchiveRun
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.ops_aggregate import (
    HierarchyMinuteAggregate,
    HttpMinuteAggregate,
    ResultCodeMinuteAggregate,
    UserCategoryMinuteAggregate,
)
from app.models.raw_event import RawEvent
from app.models.refresh_token import RefreshToken
from app.services.db_upsert import bulk_upsert_sum, declared_table
from app.services.export_job_service import purge_old_jobs
from app.services.interval_job import IntervalJob
from app.services.report_service import send_unarchived_purge_warning

logger = logging.getLogger(__name__)

# raw_events is the one table here that can hold millions of rows at real
# traffic volumes (1-3M requests/day per the product brief, RETENTION_DAYS_
# RAW_EVENTS default 7 days). Deleting a whole day's worth of aged-out rows
# in a single DELETE/transaction -- as every other table here safely does,
# since they're orders of magnitude smaller -- would hold row/page locks and
# generate a large burst of WAL for however long that delete takes to run,
# contending with the aggregator's own writes to the very same table for the
# whole purge. Deleting in small batches, each its own committed
# transaction, bounds how long any single lock is held and lets the
# aggregator's writes interleave between batches instead of queuing behind
# one multi-million-row delete. Same "big single-transaction op against a
# huge table" family of problem as the raw_events index migrations (see
# their own docstrings) -- there it was building indexes with CONCURRENTLY,
# here it's the same table's ongoing purge, so it needs the same treatment.
_RAW_EVENTS_DELETE_BATCH_SIZE = 5000


class RetentionJob(IntervalJob):
    job_name = "retention-job"
    failure_source_tag = "retention"
    failure_log_message = "Retention purge failed; will retry next interval"

    def __init__(self, interval_seconds: int = 3600) -> None:
        super().__init__(interval_seconds)
        # Populated by the most recent run() -- which branches (if any)
        # just had raw_events permanently deleted without ever being
        # archived (see _find_unarchived_branches). Read by /api/health so
        # this is visible on the dashboard, not just in logs/email; reset
        # to empty every run, so it only ever reflects the *last* purge,
        # not every warning that's ever fired.
        self.unarchived_branches: list[str] = []

    async def run(self) -> None:
        settings = get_settings()
        now = datetime.now(UTC)
        raw_cutoff = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS)
        aggregate_cutoff = now - timedelta(days=settings.RETENTION_DAYS_AGGREGATES)
        ops_cutoff = now - timedelta(days=settings.RETENTION_DAYS_OPS_AGGREGATES)
        rollup_cutoff = now - timedelta(hours=settings.CLIENT_ROLLUP_AFTER_HOURS)

        async with AsyncSessionLocal() as session:
            await self._rollup_client_minutes_to_hourly(session, rollup_cutoff)

            # Checked *before* the delete below, against the data that
            # delete is about to remove -- purging still happens either way
            # (retention has to stay bounded regardless of whether anyone's
            # archiving), this only decides whether to warn about it.
            unarchived_branches = await self._find_unarchived_branches(session, settings, raw_cutoff)
            await session.commit()

        # Its own batched, multi-transaction pass -- see
        # _RAW_EVENTS_DELETE_BATCH_SIZE's docstring above. Safe to run
        # outside the transaction below: retention is idempotent (re-running
        # against the same cutoff only ever deletes whatever's still left
        # older than it), so splitting this from the smaller tables' delete
        # below doesn't weaken the "purge eventually catches up" guarantee,
        # it just means a crash between the two leaves a bit more raw_events
        # data than aggregates for one extra cycle, not any inconsistency.
        raw_deleted = await self._delete_raw_events_before(raw_cutoff)

        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MinuteAggregate).where(MinuteAggregate.bucket_ts < aggregate_cutoff)
            )
            await session.execute(
                delete(DomainMinuteAggregate).where(
                    DomainMinuteAggregate.bucket_ts < aggregate_cutoff
                )
            )
            await session.execute(
                delete(ClientMinuteAggregate).where(
                    ClientMinuteAggregate.bucket_ts < aggregate_cutoff
                )
            )
            await session.execute(
                delete(ClientCategoryMinuteAggregate).where(
                    ClientCategoryMinuteAggregate.bucket_ts < aggregate_cutoff
                )
            )
            await session.execute(
                delete(ClientHourlyAggregate).where(ClientHourlyAggregate.bucket_ts < aggregate_cutoff)
            )
            # The Analytics "Squid ops" per-minute aggregates get their own,
            # shorter window (RETENTION_DAYS_OPS_AGGREGATES) -- higher
            # cardinality than the tables above and never queried past a few
            # days by the UI. The response-time histogram lives on
            # minute_aggregates itself and ages out with it above.
            await session.execute(
                delete(ResultCodeMinuteAggregate).where(
                    ResultCodeMinuteAggregate.bucket_ts < ops_cutoff
                )
            )
            await session.execute(
                delete(HttpMinuteAggregate).where(HttpMinuteAggregate.bucket_ts < ops_cutoff)
            )
            await session.execute(
                delete(HierarchyMinuteAggregate).where(
                    HierarchyMinuteAggregate.bucket_ts < ops_cutoff
                )
            )
            await session.execute(
                delete(UserCategoryMinuteAggregate).where(
                    UserCategoryMinuteAggregate.bucket_ts < ops_cutoff
                )
            )
            # Revoked/rotated tokens are kept until their natural expiry (a
            # theft-detection signal, see api/routes/auth.py:refresh), then
            # purged here so the table doesn't grow unbounded.
            await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
            # Export job result files (see api/routes/export.py's POST
            # /export/jobs) are meant to be downloaded soon after they
            # finish, not kept indefinitely -- purge alongside everything
            # else with its own, much shorter window.
            await purge_old_jobs(session)
            await session.commit()

        logger.info(
            "Retention purge complete",
            extra={"raw_events_deleted": raw_deleted, "raw_cutoff": raw_cutoff.isoformat()},
        )

        self.unarchived_branches = unarchived_branches
        if unarchived_branches:
            logger.warning(
                "Purged raw_events for branch(es) never archived: %s (cutoff %s)",
                ", ".join(unarchived_branches),
                raw_cutoff.isoformat(),
            )
            # A broken/unconfigured SMTP setup must never take down
            # retention itself -- the purge above already happened and
            # committed; this is a best-effort notification about it, not
            # part of the purge's own correctness.
            try:
                await send_unarchived_purge_warning(unarchived_branches, raw_cutoff)
            except Exception:
                logger.exception("Failed to send unarchived-purge warning email")

    async def _delete_raw_events_before(self, cutoff: datetime) -> int:
        """Deletes every raw_events row older than `cutoff`, in bounded
        batches each committed as its own transaction -- see
        _RAW_EVENTS_DELETE_BATCH_SIZE above for why. `id IN (subquery)`
        rather than a plain `DELETE ... LIMIT`: the latter isn't portable
        (SQLite rejects it by default; only Postgres supports it at all),
        while a LIMIT inside the id subquery works identically on both, and
        still lets the delete itself go straight to primary-key rows."""
        total_deleted = 0
        while True:
            async with AsyncSessionLocal() as session:
                batch_ids = select(RawEvent.id).where(RawEvent.timestamp < cutoff).limit(
                    _RAW_EVENTS_DELETE_BATCH_SIZE
                )
                result = await session.execute(delete(RawEvent).where(RawEvent.id.in_(batch_ids)))
                await session.commit()
                # A Core DELETE always executes through the DBAPI cursor, so
                # this is really a CursorResult at runtime -- AsyncSession
                # .execute()'s stub return type is the more general Result,
                # which doesn't declare .rowcount (only CursorResult does).
                deleted = cast(CursorResult, result).rowcount
            total_deleted += deleted
            if deleted < _RAW_EVENTS_DELETE_BATCH_SIZE:
                return total_deleted

    async def _find_unarchived_branches(
        self, session: AsyncSession, settings: Settings, raw_cutoff: datetime
    ) -> list[str]:
        """Which configured branches have raw_events about to be purged
        (older than raw_cutoff) that scripts/archive_weekly_export.py never
        archived up to that point -- i.e. ArchiveRun has no row for that
        branch, or its last successful archive didn't reach far enough."""
        archived_until_by_branch = {
            row.branch: row.archived_until
            for row in (await session.execute(select(ArchiveRun))).scalars().all()
        }
        unarchived = []
        for source in settings.effective_log_sources:
            archived_until = archived_until_by_branch.get(source.branch)
            if archived_until is None or archived_until < raw_cutoff:
                unarchived.append(source.branch)
        return unarchived

    async def _rollup_client_minutes_to_hourly(
        self, session: AsyncSession, rollup_cutoff: datetime
    ) -> None:
        """Compress client_minute_aggregates rows older than rollup_cutoff
        into client_hourly_aggregates, then delete the source minute rows.

        Runs before the deletes below in the same transaction so a rolled-up
        row is never lost between the two steps. Aggregated in Python (like
        Aggregator.flush()) rather than via INSERT...SELECT...GROUP BY,
        since truncating a timestamp to the hour isn't expressed the same
        way in SQLite vs. Postgres -- this keeps the DB-specific part
        limited to bulk_upsert_sum's dialect switch, same as everywhere else
        in this codebase.
        """
        rows = (
            await session.execute(
                select(ClientMinuteAggregate).where(ClientMinuteAggregate.bucket_ts < rollup_cutoff)
            )
        ).scalars().all()
        if not rows:
            return

        hourly_totals: dict[tuple[datetime, str, str, str | None], dict[str, int]] = defaultdict(
            lambda: {"request_count": 0, "blocked_count": 0, "total_bytes": 0}
        )
        for row in rows:
            hour_bucket = row.bucket_ts.replace(minute=0, second=0, microsecond=0)
            totals = hourly_totals[(hour_bucket, row.client_ip, row.branch, row.user)]
            totals["request_count"] += row.request_count
            totals["blocked_count"] += row.blocked_count
            totals["total_bytes"] += row.total_bytes

        hourly_rows = [
            {"bucket_ts": bucket_ts, "client_ip": client_ip, "branch": branch, "user": user, **totals}
            for (bucket_ts, client_ip, branch, user), totals in hourly_totals.items()
        ]
        await bulk_upsert_sum(
            session,
            declared_table(ClientHourlyAggregate),
            hourly_rows,
            index_elements=[
                ClientHourlyAggregate.bucket_ts,
                ClientHourlyAggregate.client_ip,
                ClientHourlyAggregate.branch,
                func.coalesce(ClientHourlyAggregate.user, literal_column("''")),
            ],
            sum_columns=["request_count", "blocked_count", "total_bytes"],
        )
        await session.execute(
            delete(ClientMinuteAggregate).where(ClientMinuteAggregate.bucket_ts < rollup_cutoff)
        )
