"""Periodic purge of data past its configured retention window, plus
compressing aged-out client minute data into hourly rows first.

Raw events and aggregates are purged on independent schedules
(RETENTION_DAYS_RAW_EVENTS vs. RETENTION_DAYS_AGGREGATES) since aggregates
are cheap to keep for long-term trend reporting while raw per-event detail
is comparatively expensive to retain.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.archive_run import ArchiveRun
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.refresh_token import RefreshToken
from app.services.db_upsert import bulk_upsert_sum
from app.services.report_service import send_unarchived_purge_warning

logger = logging.getLogger(__name__)


class RetentionJob:
    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # Populated by the most recent purge() -- which branches (if any)
        # just had raw_events permanently deleted without ever being
        # archived (see _find_unarchived_branches). Read by /api/health so
        # this is visible on the dashboard, not just in logs/email; reset
        # to empty every run, so it only ever reflects the *last* purge,
        # not every warning that's ever fired.
        self.unarchived_branches: list[str] = []

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever(), name="retention-job")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()

    async def _run_forever(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except TimeoutError:
                await self._purge_catching_errors()

    async def _purge_catching_errors(self) -> None:
        """A single bad purge must never permanently stop retention -- see
        Aggregator._flush_catching_errors for the same reasoning."""
        try:
            await self.purge()
        except Exception:
            logger.exception("Retention purge failed; will retry next interval")

    async def purge(self) -> None:
        settings = get_settings()
        now = datetime.now(UTC)
        raw_cutoff = now - timedelta(days=settings.RETENTION_DAYS_RAW_EVENTS)
        aggregate_cutoff = now - timedelta(days=settings.RETENTION_DAYS_AGGREGATES)
        rollup_cutoff = now - timedelta(hours=settings.CLIENT_ROLLUP_AFTER_HOURS)

        async with AsyncSessionLocal() as session:
            await self._rollup_client_minutes_to_hourly(session, rollup_cutoff)

            # Checked *before* the delete below, against the data that
            # delete is about to remove -- purging still happens either way
            # (retention has to stay bounded regardless of whether anyone's
            # archiving), this only decides whether to warn about it.
            unarchived_branches = await self._find_unarchived_branches(session, settings, raw_cutoff)

            raw_result = await session.execute(delete(RawEvent).where(RawEvent.timestamp < raw_cutoff))
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
            # Revoked/rotated tokens are kept until their natural expiry (a
            # theft-detection signal, see api/routes/auth.py:refresh), then
            # purged here so the table doesn't grow unbounded.
            await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
            await session.commit()

        logger.info(
            "Retention purge complete",
            extra={"raw_events_deleted": raw_result.rowcount, "raw_cutoff": raw_cutoff.isoformat()},
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
            ClientHourlyAggregate.__table__,
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
