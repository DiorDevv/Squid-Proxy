"""Periodic purge of data past its configured retention window.

Raw events and aggregates are purged on independent schedules
(RETENTION_DAYS_RAW_EVENTS vs. RETENTION_DAYS_AGGREGATES) since aggregates
are cheap to keep for long-term trend reporting while raw per-event detail
is comparatively expensive to retain.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import get_settings
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.refresh_token import RefreshToken

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

        async with AsyncSessionLocal() as session:
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
            # Revoked/rotated tokens are kept until their natural expiry (a
            # theft-detection signal, see api/routes/auth.py:refresh), then
            # purged here so the table doesn't grow unbounded.
            await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
            await session.commit()

        logger.info(
            "Retention purge complete",
            extra={"raw_events_deleted": raw_result.rowcount, "raw_cutoff": raw_cutoff.isoformat()},
        )
