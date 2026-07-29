"""Tails a Squid access.log file in real time, robust to log rotation.

Handles both common logrotate strategies:
  - "create" mode: the file is renamed/removed and a new file is created at
    the same path (inode changes).
  - "copytruncate" mode: the file is copied elsewhere then truncated in
    place (inode stays the same, size drops below our last-read offset).

If the file is briefly missing, retries with exponential backoff instead of
crashing the process.

All blocking file I/O (open/stat/read) and the CPU-bound parsing loop run
inside a worker thread via `asyncio.to_thread` -- reading a large backlog in
one go (e.g. rsyslog draining a queue built up during a branch/central-link
outage, see README's "Multi-branch deployment") measured at 3.6s for 200k
lines against this file's earlier synchronous version, during which the
single-threaded event loop couldn't serve a single API request or WebSocket
push. Only `on_event` (which may schedule asyncio tasks -- see
WebSocketManager.broadcast_nowait) is dispatched back on the event-loop
thread, since asyncio primitives aren't safe to touch from a worker thread.

Read position (inode + byte offset) is persisted to `state_dir` (if set)
after every poll, so a routine restart (deploy, crash, systemd
Restart=on-failure) resumes exactly where it left off instead of silently
skipping whatever was written while the process was down -- previously
every fresh LogTailer always opened at the file's current end, regardless
of whether this was truly the first run or just a restart.
"""

import asyncio
import contextlib
import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from app.services.log_parser import ParsedEvent, parse_line

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 0.5


def _state_file_path(state_dir: str, branch: str) -> Path:
    # Branch names come from trusted config (LOG_SOURCES), but are
    # sanitized anyway before use as a filename -- cheap insurance against
    # an unusual branch name producing an invalid or unexpected path.
    safe_branch = re.sub(r"[^a-zA-Z0-9_-]", "_", branch) or "default"
    return Path(state_dir) / f"{safe_branch}.json"


def _load_persisted_state(state_dir: str, branch: str) -> dict | None:
    path = _state_file_path(state_dir, branch)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("inode"), int) and isinstance(data.get("offset"), int):
            return data
    except (OSError, ValueError, AttributeError):
        # Missing file (never persisted yet), corrupt JSON, or unexpected
        # shape -- all treated the same as "no usable prior state", never
        # a reason to crash the tailer.
        pass
    return None


def _save_persisted_state(state_dir: str, branch: str, inode: int, offset: int) -> None:
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    path = _state_file_path(state_dir, branch)
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"inode": inode, "offset": offset}, f)
    os.replace(tmp_path, path)  # atomic on POSIX -- never leaves a half-written state file


class LogTailer:
    def __init__(
        self,
        path: str,
        on_event: Callable[[ParsedEvent], None],
        branch: str,
        poll_interval: float = 0.75,
        backoff_max: float = 30.0,
        state_dir: str | None = None,
    ) -> None:
        self.path = path
        self.on_event = on_event
        self.branch = branch
        self.poll_interval = poll_interval
        self.backoff_max = backoff_max
        # None (the default) disables position persistence entirely, e.g.
        # for tests that construct a LogTailer directly and don't want
        # incidental state files -- see app/main.py for the real
        # deployment's wiring (LOG_TAILER_STATE_DIR, on by default there).
        self.state_dir = state_dir

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
        """Run one tail iteration. Returns True if the log file was unavailable.

        The blocking/CPU-bound work happens in a worker thread (see
        _poll_once_sync); only dispatching already-parsed events to
        `on_event` happens here, back on the event-loop thread, since that
        callback may touch asyncio state (WebSocketManager schedules tasks
        on the running loop, which is only safe from the thread that owns
        it)."""
        try:
            missing, events = await asyncio.to_thread(self._poll_once_sync)
        except Exception:
            logger.exception("Unexpected error while tailing log file", extra={"path": self.path})
            self._alive = False
            self._close()
            return True

        if missing:
            self._alive = False
            return True

        self._alive = True
        try:
            for event in events:
                self.on_event(event)
        except Exception:
            # The file position (and, if state_dir is set, the persisted
            # position) already reflects everything read this poll,
            # regardless of whether every event was successfully delivered
            # here -- so this deliberately does NOT close/reopen the file.
            # Doing so would just skip ahead to the current EOF and lose
            # more, rather than fixing anything: read-position tracking and
            # downstream delivery are separate concerns, and re-reading
            # already-read bytes isn't possible once _partial has moved on.
            logger.exception(
                "Error dispatching parsed event(s) to on_event", extra={"path": self.path}
            )
        return False

    def _poll_once_sync(self) -> tuple[bool, list[ParsedEvent]]:
        """Everything in this method (and what it calls) runs inside a
        worker thread via asyncio.to_thread -- must stay free of anything
        asyncio-bound. Returns (was_missing, parsed_events)."""
        if self._fh is None:
            self._open_initial()

        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            self._close()
            return True, []

        events: list[ParsedEvent] = []
        position_changed = False
        if st.st_ino != self._inode:
            events += self._handle_create_rotation()
            position_changed = True
        elif self._fh is not None and st.st_size < self._fh.tell():
            self._handle_truncate_rotation()
            position_changed = True

        new_events, bytes_read = self._read_available()
        events += new_events

        # Only touch disk when the position actually moved -- an idle log
        # (no new traffic) would otherwise mean one small write+atomic-rename
        # every poll_interval forever (e.g. ~115k/day per branch at the
        # 0.75s default), for a position that never changed.
        if position_changed or bytes_read:
            self._persist_state()
        return False, events

    def _open_initial(self) -> None:
        """The very first open for this LogTailer instance -- resumes from a
        previously-persisted position if one exists and still matches this
        file (same inode), so a routine restart doesn't silently skip
        whatever was written while the process was down. Otherwise:

        - a saved position exists but for a *different* inode (the file was
          rotated away while this process was down) -- starts from the
          beginning of the *current* file, which correctly captures
          everything written to it since the rotation (we have no way to
          recover whatever was left unread in the now-gone old file, but
          starting at 0 here reads everything the new file actually has).
        - no saved state at all (this tailer has never run before) -- opens
          at the current end of file, deliberately skipping whatever
          historical content already exists, matching this project's
          documented "don't ingest a possibly-massive pre-existing log on
          first deploy" behavior.
        """
        # newline="" disables universal-newline translation: without it, a
        # bare \r anywhere in a line (e.g. a raw control byte Squid logged
        # verbatim from a malformed request URL -- confirmed against a real
        # multi-million-line access.log, where ~2.3M such bytes fragmented
        # ~35% of otherwise well-formed lines into garbage) is treated as an
        # extra line boundary by Python's text-mode reader, silently
        # shredding real records before _flush_complete_lines's own explicit
        # split("\n") ever sees them. Splitting on "\n" only, ourselves,
        # matches both wc -l's definition of a line and how Squid actually
        # terminates records.
        fh = open(self.path, encoding="utf-8", errors="replace", newline="")  # noqa: SIM115
        inode = os.fstat(fh.fileno()).st_ino
        state = self._load_state()

        if state is not None and state["inode"] == inode:
            fh.seek(state["offset"])
        elif state is not None:
            fh.seek(0)
        else:
            fh.seek(0, os.SEEK_END)

        self._fh = fh
        self._inode = inode
        self._partial = ""

    def _open_at_start(self) -> None:
        fh = open(self.path, encoding="utf-8", errors="replace", newline="")  # noqa: SIM115
        self._fh = fh
        self._inode = os.fstat(fh.fileno()).st_ino
        self._partial = ""

    def _handle_create_rotation(self) -> list[ParsedEvent]:
        logger.info("Detected log rotation (inode changed), draining old file", extra={"path": self.path})
        events: list[ParsedEvent] = []
        if self._fh is not None:
            remainder = self._fh.read()
            self._partial += remainder
            events = self._flush_complete_lines()
            self._fh.close()
        self._open_at_start()
        return events

    def _handle_truncate_rotation(self) -> None:
        logger.info("Detected log truncation (copytruncate), seeking to start", extra={"path": self.path})
        assert self._fh is not None
        self._fh.seek(0)
        self._partial = ""

    def _read_available(self) -> tuple[list[ParsedEvent], int]:
        assert self._fh is not None
        chunk = self._fh.read()
        if not chunk:
            return [], 0
        self._partial += chunk
        return self._flush_complete_lines(), len(chunk)

    _SUMMARY_CHECK_INTERVAL = 1000
    _SUMMARY_FAILURE_THRESHOLD = 0.5

    def _flush_complete_lines(self) -> list[ParsedEvent]:
        lines = self._partial.split("\n")
        self._partial = lines.pop()
        events: list[ParsedEvent] = []
        for line in lines:
            if not line.strip():
                continue
            self._lines_seen += 1
            event = parse_line(line, branch=self.branch)
            if event is not None:
                self._lines_parsed += 1
                events.append(event)
            if self._lines_seen % self._SUMMARY_CHECK_INTERVAL == 0:
                self._log_parse_health_summary()
        return events

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

    def _load_state(self) -> dict | None:
        if self.state_dir is None:
            return None
        return _load_persisted_state(self.state_dir, self.branch)

    def _persist_state(self) -> None:
        if self.state_dir is None or self._fh is None or self._inode is None:
            return
        try:
            _save_persisted_state(self.state_dir, self.branch, self._inode, self._fh.tell())
        except OSError:
            logger.warning("Failed to persist log tailer position", extra={"path": self.path})

    def _close(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(OSError):
                self._fh.close()
        self._fh = None
        self._inode = None
