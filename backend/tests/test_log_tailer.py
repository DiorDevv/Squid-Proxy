import os
from pathlib import Path

from app.services.log_tailer import LogTailer


def squid_line(domain: str = "example.com") -> str:
    return f"1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET http://{domain}/ alice HIER_DIRECT/93.184.216.34 text/html\n"


def make_tailer(path: Path) -> tuple[LogTailer, list]:
    events = []
    tailer = LogTailer(path=str(path), on_event=events.append, poll_interval=0.01, backoff_max=1.0)
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
