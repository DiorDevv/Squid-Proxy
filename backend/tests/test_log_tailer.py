import asyncio
import os
import time
from pathlib import Path

from app.services.log_tailer import LogTailer


def squid_line(domain: str = "example.com") -> str:
    return f"1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://{domain}/ alice HIER_DIRECT/93.184.216.34 text/html\n"


def make_tailer(path: Path, state_dir: Path | None = None) -> tuple[LogTailer, list]:
    events = []
    tailer = LogTailer(
        path=str(path),
        on_event=events.append,
        branch="default",
        poll_interval=0.01,
        backoff_max=1.0,
        state_dir=str(state_dir) if state_dir else None,
    )
    return tailer, events


async def test_tails_only_new_lines_written_after_start(tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text(squid_line("pre-existing.com"))

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()  # first poll opens at EOF, skipping pre-existing content
    assert events == []

    with log_path.open("a") as f:
        f.write(squid_line("new.com"))

    await tailer.poll_once()
    assert len(events) == 1
    assert events[0].domain == "new.com"


async def test_missing_file_reports_unavailable_and_does_not_raise(tmp_path):
    missing_path = tmp_path / "does-not-exist.log"
    tailer, events = make_tailer(missing_path)

    was_missing = await tailer.poll_once()

    assert was_missing is True
    assert tailer.is_alive is False
    assert events == []


async def test_malformed_line_is_skipped_without_crashing(tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text("")

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()

    with log_path.open("a") as f:
        f.write("this is not a valid squid log line\n")
        f.write(squid_line("valid.com"))

    was_missing = await tailer.poll_once()

    assert was_missing is False
    assert len(events) == 1
    assert events[0].domain == "valid.com"


async def test_create_mode_rotation_drains_old_file_then_reads_new_file(tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text("")

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()  # opens at EOF of empty file

    with log_path.open("a") as f:
        f.write(squid_line("before-rotation.com"))

    rotated_path = tmp_path / "access.log.1"
    os.rename(log_path, rotated_path)
    log_path.write_text(squid_line("after-rotation.com"))

    was_missing = await tailer.poll_once()

    assert was_missing is False
    domains = [e.domain for e in events]
    assert domains == ["before-rotation.com", "after-rotation.com"]


async def test_copytruncate_rotation_seeks_to_start(tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text("")

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()

    with log_path.open("a") as f:
        f.write(squid_line("long-line-before-truncate.com"))
    await tailer.poll_once()
    assert len(events) == 1

    original_inode = os.stat(log_path).st_ino

    with log_path.open("w") as f:
        f.write(squid_line("after-truncate.com"))

    assert os.stat(log_path).st_ino == original_inode

    was_missing = await tailer.poll_once()

    assert was_missing is False
    assert [e.domain for e in events] == [
        "long-line-before-truncate.com",
        "after-truncate.com",
    ]


async def test_lines_seen_and_parsed_are_tracked(tmp_path):
    log_path = tmp_path / "access.log"
    log_path.write_text("")

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()

    with log_path.open("a") as f:
        f.write("this is not a valid squid log line\n")
        f.write(squid_line("valid.com"))

    await tailer.poll_once()

    assert tailer.lines_seen == 2
    assert tailer.lines_parsed == 1


async def test_high_failure_rate_logs_a_summary_warning(tmp_path, caplog):
    log_path = tmp_path / "access.log"
    log_path.write_text("")

    tailer, _events = make_tailer(log_path)
    tailer._SUMMARY_CHECK_INTERVAL = 10  # avoid writing 1000 lines in a test
    await tailer.poll_once()

    bad_lines = "not a valid squid log line\n" * 10
    with log_path.open("a") as f:
        f.write(bad_lines)

    import logging

    with caplog.at_level(logging.WARNING, logger="app.services.log_tailer"):
        await tailer.poll_once()

    assert tailer.lines_seen == 10
    assert tailer.lines_parsed == 0
    assert any("parse failure rate" in record.message for record in caplog.records)


async def test_embedded_carriage_return_does_not_fragment_a_line(tmp_path):
    """A raw \\r byte inside a field (e.g. an unescaped control character in
    a malformed request URL) must not be treated as an extra line boundary
    -- confirmed against a real multi-million-line production access.log,
    where ~2.3M such bytes were present and, under Python's default
    universal-newline text mode, fragmented well-formed lines into ragged
    pieces (a 69% apparent parse-failure rate that dropped to the file's
    real ~53%, all genuinely malformed non-Squid-format traffic, once this
    line-boundary bug was fixed). Squid terminates records with \\n only, so
    the file must be read the same way -- this test only asserts the line
    *count* stays correct; the \\r-containing line itself still fails to
    parse (`.split()`'s own whitespace tokenizing splits on the embedded \\r
    too, same as a real space would), which is a separate, secondary
    concern from the line-fragmentation bug this fixes."""
    log_path = tmp_path / "access.log"
    log_path.write_bytes(b"")

    tailer, events = make_tailer(log_path)
    await tailer.poll_once()  # opens at EOF of empty file

    line_with_embedded_cr = (
        b"1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET "
        b"http://exa\rmple.com/ alice HIER_DIRECT/93.184.216.34 text/html\n"
    )
    with log_path.open("ab") as f:
        f.write(line_with_embedded_cr)
        f.write(squid_line("after.com").encode())

    await tailer.poll_once()

    # Exactly two real lines were written (two trailing \n bytes) -- a
    # universal-newlines bug would count three, treating the embedded \r as
    # its own line boundary and shredding both records instead of just
    # failing to tokenize the one that actually contains it.
    assert tailer.lines_seen == 2
    assert [e.domain for e in events] == ["after.com"]
    assert [e.domain for e in events][-1] == "after.com"


async def test_backoff_recovers_once_file_reappears(tmp_path):
    log_path = tmp_path / "access.log"
    tailer, events = make_tailer(log_path)

    was_missing = await tailer.poll_once()
    assert was_missing is True

    log_path.write_text(squid_line("recovered.com"))

    was_missing = await tailer.poll_once()
    assert was_missing is False
    assert tailer.is_alive is True
    assert events == []  # file reopened at EOF again, pre-existing content skipped


async def test_resumes_from_persisted_position_after_restart(tmp_path):
    """Simulates a process restart: a second LogTailer instance, pointed at
    the same file and state_dir as the first, must resume from exactly
    where the first one left off -- not re-read (duplicates) and not skip
    ahead to the current EOF (data loss)."""
    log_path = tmp_path / "access.log"
    state_dir = tmp_path / "state"
    log_path.write_text("")

    first_tailer, first_events = make_tailer(log_path, state_dir=state_dir)
    await first_tailer.poll_once()  # opens at EOF of empty file, persists position

    with log_path.open("a") as f:
        f.write(squid_line("seen-before-restart.com"))
    await first_tailer.poll_once()
    assert [e.domain for e in first_events] == ["seen-before-restart.com"]

    # "Restart": more data is appended while nothing is tailing, then a
    # brand-new LogTailer instance (fresh in-memory state, same state_dir)
    # takes over -- exactly what happens across a real process restart.
    with log_path.open("a") as f:
        f.write(squid_line("written-while-down.com"))

    second_tailer, second_events = make_tailer(log_path, state_dir=state_dir)
    was_missing = await second_tailer.poll_once()

    assert was_missing is False
    assert [e.domain for e in second_events] == ["written-while-down.com"]


async def test_restart_mid_line_recovers_the_full_line_via_persisted_partial(tmp_path):
    """If the process restarts exactly while Squid had only flushed part of
    a line, the tailer must not lose that record: on restart it needs the
    in-flight partial text it had already buffered, not just the byte
    offset -- offset alone would resume reading right after those
    already-consumed bytes and see only the line's tail as if it were a
    fresh, malformed line, silently dropping the record instead of ever
    reassembling it once Squid finishes the write."""
    log_path = tmp_path / "access.log"
    state_dir = tmp_path / "state"
    log_path.write_text("")

    first_tailer, first_events = make_tailer(log_path, state_dir=state_dir)
    await first_tailer.poll_once()  # opens at EOF of empty file

    full_line = squid_line("mid-write.com")
    split_point = full_line.index("TCP_MISS") + 4  # partway through a field
    with log_path.open("a") as f:
        f.write(full_line[:split_point])  # no trailing "\n" -- an in-flight write
    await first_tailer.poll_once()
    assert first_events == []  # nothing complete yet, but the partial bytes are consumed

    # "Restart": a brand-new LogTailer takes over with only the persisted
    # state, then Squid finishes writing the rest of the same line.
    with log_path.open("a") as f:
        f.write(full_line[split_point:])

    second_tailer, second_events = make_tailer(log_path, state_dir=state_dir)
    was_missing = await second_tailer.poll_once()

    assert was_missing is False
    assert len(second_events) == 1
    assert second_events[0].domain == "mid-write.com"


async def test_rotation_while_down_starts_new_file_from_beginning(tmp_path):
    """If the file was rotated (logrotate 'create' mode) while the process
    was down, the persisted inode no longer matches -- the old file's
    unread tail is unrecoverable, but the new file must be read from its
    own beginning rather than skipped to EOF, since it may already contain
    data written since the rotation that's never been seen."""
    log_path = tmp_path / "access.log"
    state_dir = tmp_path / "state"
    log_path.write_text("")

    first_tailer, _first_events = make_tailer(log_path, state_dir=state_dir)
    await first_tailer.poll_once()
    with log_path.open("a") as f:
        f.write(squid_line("before-rotation-and-restart.com"))
    await first_tailer.poll_once()

    # Rotate (new inode) while "down", with fresh content already written
    # to the new file before the tailer comes back.
    os.rename(log_path, tmp_path / "access.log.1")
    log_path.write_text(squid_line("written-to-new-file-while-down.com"))

    second_tailer, second_events = make_tailer(log_path, state_dir=state_dir)
    was_missing = await second_tailer.poll_once()

    assert was_missing is False
    assert [e.domain for e in second_events] == ["written-to-new-file-while-down.com"]


async def test_no_persisted_state_opens_at_end_even_with_state_dir_configured(tmp_path):
    """state_dir being configured doesn't change first-ever-run behavior --
    only a *previous* run's persisted position does."""
    log_path = tmp_path / "access.log"
    state_dir = tmp_path / "state"
    log_path.write_text(squid_line("pre-existing.com"))

    tailer, events = make_tailer(log_path, state_dir=state_dir)
    await tailer.poll_once()

    assert events == []


async def test_idle_poll_does_not_rewrite_the_state_file(tmp_path):
    """An idle log (no new data, no rotation) shouldn't touch disk on every
    single poll -- only when the read position actually changes."""
    log_path = tmp_path / "access.log"
    state_dir = tmp_path / "state"
    log_path.write_text("")

    tailer, _events = make_tailer(log_path, state_dir=state_dir)
    await tailer.poll_once()  # opens at EOF, position changes from "no file" -> persisted

    with log_path.open("a") as f:
        f.write(squid_line("real-traffic.com"))
    await tailer.poll_once()

    state_path = state_dir / "default.json"
    mtime_after_data = state_path.stat().st_mtime_ns

    # Several idle polls in a row -- nothing new written to the log.
    for _ in range(5):
        was_missing = await tailer.poll_once()
        assert was_missing is False

    assert state_path.stat().st_mtime_ns == mtime_after_data


async def test_large_backlog_does_not_block_the_event_loop(tmp_path):
    """The old (pre-thread) implementation read+parsed synchronously on the
    event loop -- measured at 3.6s to freeze the entire process for a 200k
    line backlog (e.g. rsyslog draining a queue after a branch/central link
    recovers, see README). A concurrent heartbeat must still get scheduled
    regularly while a large poll is in flight."""
    log_path = tmp_path / "access.log"
    log_path.write_text("")
    tailer, events = make_tailer(log_path)
    await tailer.poll_once()  # opens at EOF

    line_count = 50_000
    with log_path.open("a") as f:
        f.write(squid_line() * line_count)

    heartbeat_ticks = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        while True:
            await asyncio.sleep(0.005)
            heartbeat_ticks += 1

    hb_task = asyncio.create_task(heartbeat())
    t0 = time.monotonic()
    await tailer.poll_once()
    elapsed = time.monotonic() - t0
    hb_task.cancel()

    assert len(events) == line_count
    # A blocking implementation would produce ~0 ticks for however long the
    # read+parse takes; to_thread lets the loop keep scheduling other work
    # throughout, so plenty of ticks should land during a multi-hundred-ms
    # poll.
    assert heartbeat_ticks > 5, f"only {heartbeat_ticks} heartbeat ticks during a {elapsed:.3f}s poll"
