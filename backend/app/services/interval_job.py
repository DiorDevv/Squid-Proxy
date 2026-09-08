"""Shared start/stop/retry-forever shape for every background job in this
codebase that isn't a continuous tailer (see log_tailer.py) or a per-flush
worker (see aggregator.py) -- i.e. "run a check every N seconds, catch and
report failures without ever permanently stopping, shut down cleanly."

Before this existed, all 8 subclasses below hand-rolled the identical
__init__/start/stop/_run_forever/catching-errors boilerplate, differing only
in their business method and a couple of identifier strings. Consolidating
it here means that shape only needs to be gotten right once.
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.services.ops_alerting import notify_operator_failure

logger = logging.getLogger(__name__)


class IntervalJob(ABC):
    # Set by subclasses: identifies this job's asyncio.Task (visible in
    # e.g. `asyncio.all_tasks()` during debugging) and the tag/message
    # passed to notify_operator_failure when run() raises.
    job_name: str
    failure_source_tag: str
    failure_log_message: str

    # Two of eight subclasses (ArchiveScheduler, Ut1BlacklistScheduler) need
    # their first check to fire immediately on start() rather than waiting a
    # full interval_seconds -- see their own docstrings for why. False (the
    # plain "wait, then check" loop) is the right default for the rest.
    run_immediately_on_start: bool = False

    # A random 0..N seconds *added on top of* interval_seconds before the
    # first check only. All ~9 subclasses are start()ed in a tight loop in
    # main.py and several share an interval (the 3600s category/quota/
    # uncategorized monitors), so without this they wake in lockstep and hit
    # the DB as one synchronized burst every interval. Staggering just the
    # first wait is enough -- once offset, they stay offset. It's additive
    # (never shortens the first wait) so the existing "a non-immediate job
    # does not run before its interval" guarantee still holds. Set to 0.0 in
    # a subclass (or a test) that needs the first check at a predictable time.
    max_startup_jitter_seconds: float = 60.0

    def __init__(self, interval_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # Lightweight health, surfaced by GET /api/system-health.
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None
        self.consecutive_failures: int = 0

    @property
    def is_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.run_immediately_on_start:
            # Detached on purpose (not awaited, not stored) -- start() must
            # return immediately either way, and _run_forever's own loop
            # still owns the ongoing schedule; this is strictly an extra,
            # earlier first check. A slow/failed run() here delays nothing
            # else at startup.
            asyncio.create_task(self._run_catching_errors(), name=f"{self.job_name}-initial-check")
        self._task = asyncio.create_task(self._run_forever(), name=self.job_name)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()

    async def _run_forever(self) -> None:
        # First wait is interval + jitter (see max_startup_jitter_seconds)
        # so co-started jobs don't fire in lockstep; every wait after that
        # is the plain, exact interval.
        next_wait = self.interval_seconds + random.uniform(0, self.max_startup_jitter_seconds)
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=next_wait)
                break
            except TimeoutError:
                await self._run_catching_errors()
                next_wait = self.interval_seconds

    async def _run_catching_errors(self) -> None:
        """A single bad run must never permanently stop this job -- a
        transient failure (DB hiccup, network blip) should only cost this
        one interval, not take the whole job down for good."""
        self.last_run_at = datetime.now(UTC)
        try:
            await self.run()
            self.last_error = None
            self.consecutive_failures = 0
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:500]
            self.last_error_at = datetime.now(UTC)
            self.consecutive_failures += 1
            logger.exception(self.failure_log_message)
            await notify_operator_failure(self.failure_source_tag, self.failure_log_message)

    @abstractmethod
    async def run(self) -> None: ...
