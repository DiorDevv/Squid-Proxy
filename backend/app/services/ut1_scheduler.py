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
from app.services.interval_job import IntervalJob
from app.services.ut1_blacklist import refresh

logger = logging.getLogger(__name__)


class Ut1BlacklistScheduler(IntervalJob):
    job_name = "ut1-blacklist-scheduler"
    failure_source_tag = "ut1_scheduler"
    failure_log_message = "UT1 blacklist refresh failed; will retry next interval"
    run_immediately_on_start = True

    def __init__(self, interval_seconds: int = 604800) -> None:
        super().__init__(interval_seconds)

    async def run(self) -> None:
        settings = get_settings()
        if not settings.UT1_ENABLED:
            return

        blacklist = await asyncio.to_thread(
            refresh, Path(settings.UT1_DATA_DIR), settings.UT1_MIRROR_URL
        )
        category_inference.set_ut1_blacklist(blacklist)
