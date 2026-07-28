"""Periodically refreshes the UT1 domain blacklist (see ut1_blacklist.py)
and swaps it into category_inference.py so infer_category() starts using
it immediately, no restart needed.

Two differences from this codebase's other schedulers (RetentionJob,
ArchiveScheduler), both deliberate:

1. An immediate refresh attempt on start(), not just a wait-then-check loop.
   The others can afford to wait a full interval before their first run
   (an hour before the first retention purge is harmless) -- but
   UT1_REFRESH_INTERVAL_SECONDS defaults to a week, and leaving automatic
   categorization off for a week after every fresh deployment would be a
   poor default. Startup isn't blocked on this: it's fired as a background
   task, so a slow/failed download never delays the app becoming ready.

2. The actual refresh (network download + hashing ~4.6M+ lines) runs via
   asyncio.to_thread rather than being awaited directly on the event loop --
   it's the one scheduler in this codebase with a genuinely CPU-heavy step
   (several seconds of pure-Python hashing), which would otherwise stall
   every concurrent request/WebSocket push for that long.
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.services import category_inference
from app.services.ut1_blacklist import refresh

logger = logging.getLogger(__name__)


class Ut1BlacklistScheduler:
    def __init__(self, interval_seconds: int = 604800) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        asyncio.create_task(self._check_catching_errors(), name="ut1-initial-load")
        self._task = asyncio.create_task(self._run_forever(), name="ut1-blacklist-scheduler")

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
        """A bad refresh (network down, UT1 mirror unreachable, ...) must
        never crash the app or permanently stop future attempts -- same
        reasoning as every other scheduler's _*_catching_errors wrapper.
        category_inference simply keeps using whatever blacklist (possibly
        none) it already had."""
        try:
            await self.check()
        except Exception:
            logger.exception("UT1 blacklist refresh failed; will retry next interval")

    async def check(self) -> None:
        settings = get_settings()
        if not settings.UT1_ENABLED:
            return

        blacklist = await asyncio.to_thread(
            refresh, Path(settings.UT1_DATA_DIR), settings.UT1_MIRROR_URL
        )
        category_inference.set_ut1_blacklist(blacklist)
