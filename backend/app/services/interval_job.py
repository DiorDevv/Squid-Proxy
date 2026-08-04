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
from abc import ABC, abstractmethod

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

    def __init__(self, interval_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

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
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except TimeoutError:
                await self._run_catching_errors()

    async def _run_catching_errors(self) -> None:
        """A single bad run must never permanently stop this job -- a
        transient failure (DB hiccup, network blip) should only cost this
        one interval, not take the whole job down for good."""
        try:
            await self.run()
        except Exception:
            logger.exception(self.failure_log_message)
            await notify_operator_failure(self.failure_source_tag, self.failure_log_message)

    @abstractmethod
    async def run(self) -> None: ...
