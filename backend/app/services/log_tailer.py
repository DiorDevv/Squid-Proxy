"""Tails a Squid access.log file in real time, robust to log rotation.

Handles both common logrotate strategies:
  - "create" mode: the file is renamed/removed and a new file is created at
    the same path (inode changes).
  - "copytruncate" mode: the file is copied elsewhere then truncated in
    place (inode stays the same, size drops below our last-read offset).

If the file is briefly missing, retries with exponential backoff instead of
crashing the process.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable
from typing import TextIO

from app.services.log_parser import ParsedEvent, parse_line

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 0.5


class LogTailer:
    def __init__(
        self,
        path: str,
        on_event: Callable[[ParsedEvent], None],
        branch: str,
        poll_interval: float = 0.75,
        backoff_max: float = 30.0,
    ) -> None:
        self.path = path
        self.on_event = on_event
        self.branch = branch
        self.poll_interval = poll_interval
        self.backoff_max = backoff_max

        self._fh: TextIO | None = None
        self._inode: int | None = None
        self._partial = ""
        self._alive = False
        self._backoff = INITIAL_BACKOFF_SECONDS
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Counts every non-blank line seen vs. how many parse_line() actually
        # accepted -- a healthy tailer can be "alive" (the file exists and is
        # being read) while every single line fails to parse, e.g. because a
        # real Squid install's access_log directive uses "combined" instead
        # of the "squid" native format this parser expects. That failure mode
        # produces an empty dashboard with no error anywhere, so it must be
        # visible from the outside (see /api/health) rather than only as
        # WARNING log lines an operator has to go looking for.
        self._lines_seen = 0
        self._lines_parsed = 0

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def lines_seen(self) -> int:
        return self._lines_seen

    @property
    def lines_parsed(self) -> int:
        return self._lines_parsed

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever(), name="log-tailer")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except TimeoutError:
                self._task.cancel()
        self._close()

    async def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            missing = await self.poll_once()
            if missing:
                logger.warning(
                    "Log file unavailable, retrying with backoff",
                    extra={"path": self.path, "backoff_seconds": self._backoff},
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, self.backoff_max)
            else:
                self._backoff = INITIAL_BACKOFF_SECONDS
                await asyncio.sleep(self.poll_interval)
        self._close()

    async def poll_once(self) -> bool:
        """Run one tail iteration. Returns True if the log file was unavailable."""
        try:
            if self._fh is None:
                self._open_at_end()

            try:
                st = os.stat(self.path)
            except FileNotFoundError:
                self._alive = False
                self._close()
                return True

            if st.st_ino != self._inode:
                self._handle_create_rotation()
            elif self._fh is not None and st.st_size < self._fh.tell():
                self._handle_truncate_rotation()

            self._read_available()
            self._alive = True
            return False
        except Exception:
            logger.exception("Unexpected error while tailing log file", extra={"path": self.path})
            self._alive = False
            self._close()
            return True

    def _open_at_end(self) -> None:
        # File handle is intentionally kept open across many poll_once()
        # calls, not scoped to a `with` block.
        fh = open(self.path, encoding="utf-8", errors="replace")  # noqa: SIM115
        fh.seek(0, os.SEEK_END)
        self._fh = fh
        self._inode = os.fstat(fh.fileno()).st_ino
        self._partial = ""

    def _open_at_start(self) -> None:
        fh = open(self.path, encoding="utf-8", errors="replace")  # noqa: SIM115
        self._fh = fh
        self._inode = os.fstat(fh.fileno()).st_ino
        self._partial = ""

    def _handle_create_rotation(self) -> None:
        logger.info("Detected log rotation (inode changed), draining old file", extra={"path": self.path})
        if self._fh is not None:
            remainder = self._fh.read()
            self._partial += remainder
            self._flush_complete_lines()
            self._fh.close()
        self._open_at_start()

    def _handle_truncate_rotation(self) -> None:
        logger.info("Detected log truncation (copytruncate), seeking to start", extra={"path": self.path})
        assert self._fh is not None
        self._fh.seek(0)
        self._partial = ""

    def _read_available(self) -> None:
        assert self._fh is not None
        chunk = self._fh.read()
        if not chunk:
            return
        self._partial += chunk
        self._flush_complete_lines()

    _SUMMARY_CHECK_INTERVAL = 1000
    _SUMMARY_FAILURE_THRESHOLD = 0.5

    def _flush_complete_lines(self) -> None:
        lines = self._partial.split("\n")
        self._partial = lines.pop()
        for line in lines:
            if not line.strip():
                continue
            self._lines_seen += 1
            event = parse_line(line, branch=self.branch)
            if event is not None:
                self._lines_parsed += 1
                self.on_event(event)
            if self._lines_seen % self._SUMMARY_CHECK_INTERVAL == 0:
                self._log_parse_health_summary()

    def _log_parse_health_summary(self) -> None:
        failure_rate = 1 - (self._lines_parsed / self._lines_seen)
        if failure_rate < self._SUMMARY_FAILURE_THRESHOLD:
            return
        # A high, sustained failure rate almost always means the real
        # access_log's logformat doesn't match what parse_line() expects
        # (see log_parser.py's docstring for the required field layout) --
        # one summary line per interval instead of one WARNING per bad line,
        # since at this failure rate that would be every line.
        logger.warning(
            "High log parse failure rate -- check that Squid's access_log "
            "directive uses the 'squid' native logformat, not 'common'/'combined' "
            "or a custom format (see README's Squid configuration section)",
            extra={
                "path": self.path,
                "lines_seen": self._lines_seen,
                "lines_parsed": self._lines_parsed,
                "failure_rate": round(failure_rate, 3),
            },
        )

    def _close(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(OSError):
                self._fh.close()
        self._fh = None
        self._inode = None
