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

from app.core.config import get_settings
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.refresh_token import RefreshToken
from app.services.db_upsert import bulk_upsert_sum

logger = logging.getLogger(__name__)


class RetentionJob:
    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

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

        hourly_totals: dict[tuple[datetime, str, str | None], dict[str, int]] = defaultdict(
            lambda: {"request_count": 0, "blocked_count": 0, "total_bytes": 0}
        )
        for row in rows:
            hour_bucket = row.bucket_ts.replace(minute=0, second=0, microsecond=0)
            totals = hourly_totals[(hour_bucket, row.client_ip, row.user)]
            totals["request_count"] += row.request_count
            totals["blocked_count"] += row.blocked_count
            totals["total_bytes"] += row.total_bytes

        hourly_rows = [
            {"bucket_ts": bucket_ts, "client_ip": client_ip, "user": user, **totals}
            for (bucket_ts, client_ip, user), totals in hourly_totals.items()
        ]
        await bulk_upsert_sum(
            session,
            ClientHourlyAggregate.__table__,
            hourly_rows,
            index_elements=[
                ClientHourlyAggregate.bucket_ts,
                ClientHourlyAggregate.client_ip,
                func.coalesce(ClientHourlyAggregate.user, literal_column("''")),
            ],
            sum_columns=["request_count", "blocked_count", "total_bytes"],
        )
        await session.execute(
            delete(ClientMinuteAggregate).where(ClientMinuteAggregate.bucket_ts < rollup_cutoff)
        )
