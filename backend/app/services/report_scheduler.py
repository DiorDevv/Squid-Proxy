"""Sends a periodic summary report by email on the schedule configured via
REPORT_SCHEDULE ("daily" | "weekly"). A no-op entirely when
REPORT_SCHEDULE is "disabled" or REPORT_RECIPIENTS is empty -- see
report_service.generate_and_send_report for the actual send.

Checks fairly often (REPORT_SCHEDULER_CHECK_INTERVAL_SECONDS, default 15
minutes) but only ever sends once the configured interval has actually
elapsed since last_sent_at (persisted in report_schedule_state, see
app/models/report_schedule_state.py) -- so a restart mid-interval doesn't
cause a duplicate or missed send the way an in-memory timestamp would.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.db import AsyncSessionLocal
from app.models.report_schedule_state import ReportScheduleState
from app.services.report_service import generate_and_send_report

logger = logging.getLogger(__name__)

STATE_ROW_ID = 1

_SCHEDULE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}


class ReportScheduler:
    def __init__(self, interval_seconds: int = 900) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever(), name="report-scheduler")

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
                await self._check_catching_errors()

    async def _check_catching_errors(self) -> None:
        """A single bad check must never permanently stop this job -- see
        RetentionJob._purge_catching_errors for the same reasoning."""
        try:
            await self.check()
        except Exception:
            logger.exception("Report scheduler check failed; will retry next interval")

    async def check(self) -> None:
        settings = get_settings()
        schedule_interval = _SCHEDULE_INTERVALS.get(settings.REPORT_SCHEDULE)
        if schedule_interval is None or not settings.REPORT_RECIPIENTS:
            return

        now = datetime.now(UTC)
        async with AsyncSessionLocal() as session:
            state = await self._get_state(session)
            if state.last_sent_at is not None and now - state.last_sent_at < schedule_interval:
                return

            since = state.last_sent_at or (now - schedule_interval)
            sent = await generate_and_send_report(session, since, now)
            if not sent:
                return

            state.last_sent_at = now
            session.add(state)
            await session.commit()

        logger.info(
            "Scheduled report sent", extra={"since": since.isoformat(), "until": now.isoformat()}
        )

    async def _get_state(self, session: AsyncSession) -> ReportScheduleState:
        row = (
            await session.execute(
                select(ReportScheduleState).where(ReportScheduleState.id == STATE_ROW_ID)
            )
        ).scalar_one_or_none()
        if row is None:
            row = ReportScheduleState(id=STATE_ROW_ID, last_sent_at=None)
        return row
