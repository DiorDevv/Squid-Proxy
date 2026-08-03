"""Calls app.services.archive_service.archive on a schedule -- see that
module's docstring for what archiving does and, importantly, why it isn't
cheap to call too often: each call re-covers a deliberately-overlapping,
roughly flat 7-day window rather than a lean incremental diff.

That's why this follows ReportScheduler's two-timescale shape rather than
RetentionJob's plain fixed-interval loop: check often
(ARCHIVE_CHECK_INTERVAL_SECONDS, e.g. hourly) so a restart never leaves this
waiting a full interval-from-scratch again, but only actually call archive()
once ARCHIVE_MIN_INTERVAL_SECONDS (default weekly) has genuinely elapsed
since the oldest branch's last successful run.

start() also fires one immediate check (see Ut1BlacklistScheduler.start()
for the same pattern and its own reasoning) rather than only the
_run_forever loop below, which would otherwise wait a full
check_interval_seconds before ever looking. Without this, a fresh
deployment has no ArchiveRun row for any branch until that first wait
elapses -- and RetentionJob.purge() runs on that same default interval, so
whichever of the two happens to fire first each hour is a coin flip. If
retention's purge wins that race even once, it correctly-but-confusingly
logs/surfaces "purged raw_events never archived" for a branch that, in
truth, had nothing old enough to purge yet and was about to be archived
moments later anyway. Firing archiving's first check immediately removes
that race for the common case: by the time retention's own first purge can
possibly run (still gated on its own interval), archiving has already
established an ArchiveRun row covering `now`.

Unlike ReportScheduler, there's no separate persisted "last checked" state
table to maintain here -- ArchiveRun.archived_until (upserted per-branch by
archive() itself) already durably records the answer, so "is a run due" is
just a query against data archive() already needs to touch anyway. This also
means the interval check survives restarts correctly for free: an in-memory
timer would reset to zero on every restart (as RetentionJob's does, harmless
there since a purge running a little late costs nothing), but archiving
needs to have actually happened before the 7-day retention cutoff, so basing
"due" on durable state instead of an in-memory clock matters more here.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.archive_run import ArchiveRun
from app.models.db import AsyncSessionLocal
from app.services.archive_service import archive
from app.services.ops_alerting import notify_operator_failure

logger = logging.getLogger(__name__)


class ArchiveScheduler:
    def __init__(self, check_interval_seconds: int = 3600, min_interval_seconds: int = 604800) -> None:
        self.check_interval_seconds = check_interval_seconds
        self.min_interval_seconds = min_interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        # Detached on purpose (not awaited, not stored) -- start() must
        # return immediately either way, and _run_forever's own loop below
        # still owns the ongoing schedule; this is strictly an extra,
        # earlier first check. A slow/failed archive() here delays nothing
        # else at startup (same reasoning as Ut1BlacklistScheduler.start()).
        asyncio.create_task(self._check_catching_errors(), name="archive-scheduler-initial-check")
        self._task = asyncio.create_task(self._run_forever(), name="archive-scheduler")

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
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval_seconds)
                break
            except TimeoutError:
                await self._check_catching_errors()

    async def _check_catching_errors(self) -> None:
        """A single bad check must never permanently stop this job -- see
        RetentionJob._purge_catching_errors for the same reasoning."""
        try:
            await self.check()
        except Exception:
            logger.exception("Archive scheduler check failed; will retry next interval")
            await notify_operator_failure(
                "archive_scheduler", "Archive scheduler check failed; will retry next interval"
            )

    async def check(self) -> None:
        settings = get_settings()
        if not settings.ARCHIVE_ENABLED:
            return
        if not await self._is_due(settings):
            return

        logger.info("Archive run due, starting")
        await archive(Path(settings.ARCHIVE_OUTPUT_DIR), settings.ARCHIVE_KEEP_DAYS)

    async def _is_due(self, settings: Settings) -> bool:
        """True if any configured branch either has no ArchiveRun yet, or
        its last run is older than min_interval_seconds -- i.e. calling
        archive() now would actually cover new ground for at least one
        branch, not just redundantly re-export the same week again."""
        now = datetime.now(UTC)
        async with AsyncSessionLocal() as session:
            for source in settings.effective_log_sources:
                run = await session.get(ArchiveRun, source.branch)
                if run is None or now - run.archived_until >= timedelta(seconds=self.min_interval_seconds):
                    return True
        return False
