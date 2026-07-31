"""Tests for the "is a run actually due yet" decision
(app/services/archive_scheduler.py). Patches archive_service.archive itself
(covered by its own tests in test_archive_service.py) rather than exercising
real file I/O here -- this file is purely about the scheduling decision."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.archive_run import ArchiveRun
from app.services import archive_scheduler as scheduler_module
from app.services.archive_scheduler import ArchiveScheduler


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", lambda: db_session)


def _fake_archive(calls: list):
    async def _fake(output_dir, keep_days):
        calls.append((output_dir, keep_days))

    return _fake


async def test_check_is_noop_when_disabled(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings(ARCHIVE_ENABLED=False))
    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    await ArchiveScheduler().check()

    assert calls == []


async def test_check_runs_on_first_check_with_no_prior_archive_run(
    monkeypatch, db_session: AsyncSession
):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(ARCHIVE_ENABLED=True, ARCHIVE_OUTPUT_DIR="./archives", ARCHIVE_KEEP_DAYS=30),
    )
    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    await ArchiveScheduler().check()

    assert len(calls) == 1
    assert str(calls[0][0]) == "archives"
    assert calls[0][1] == 30


async def test_check_does_not_run_again_before_min_interval_elapses(
    monkeypatch, db_session: AsyncSession
):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings(ARCHIVE_ENABLED=True))
    db_session.add(ArchiveRun(branch="default", archived_until=datetime.now(UTC) - timedelta(days=1)))
    await db_session.commit()

    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    await ArchiveScheduler(min_interval_seconds=604800).check()  # 7 days

    assert calls == []


async def test_check_runs_again_once_min_interval_has_elapsed(monkeypatch, db_session: AsyncSession):
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings(ARCHIVE_ENABLED=True))
    db_session.add(ArchiveRun(branch="default", archived_until=datetime.now(UTC) - timedelta(days=8)))
    await db_session.commit()

    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    await ArchiveScheduler(min_interval_seconds=604800).check()  # 7 days

    assert len(calls) == 1


async def test_check_survives_a_restart_that_resets_any_in_memory_timer(
    monkeypatch, db_session: AsyncSession
):
    """The whole point of basing "due" on ArchiveRun (durable) rather than an
    in-memory elapsed-time counter: a brand new ArchiveScheduler instance
    (as a restart would create) must still correctly see a run as overdue,
    with no state of its own carried over."""
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Settings(ARCHIVE_ENABLED=True))
    db_session.add(ArchiveRun(branch="default", archived_until=datetime.now(UTC) - timedelta(days=30)))
    await db_session.commit()

    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    # A fresh instance, exactly as a process restart would produce -- no
    # constructor args carry any prior "last checked" state.
    await ArchiveScheduler().check()

    assert len(calls) == 1


async def test_start_fires_an_immediate_check_without_waiting_a_full_interval(
    monkeypatch, db_session: AsyncSession
):
    """Regression test for the race this fixes: start() used to only
    schedule _run_forever's loop, which waits check_interval_seconds before
    its very first check. On a fresh deployment (no ArchiveRun rows yet),
    that left a window where RetentionJob's own first purge (same default
    interval, see retention.py) could run before archiving ever had, and
    log a spurious "purged raw_events never archived" warning for data that
    had nothing old enough to purge yet and was about to be archived
    moments later anyway. See this module's start() docstring."""
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: Settings(ARCHIVE_ENABLED=True, ARCHIVE_OUTPUT_DIR="./archives", ARCHIVE_KEEP_DAYS=30),
    )
    calls: list = []
    monkeypatch.setattr(scheduler_module, "archive", _fake_archive(calls))

    # A long interval -- if start() only relied on _run_forever's loop, this
    # test would have to wait an hour (real or mocked clock) to see a call.
    scheduler = ArchiveScheduler(check_interval_seconds=3600)
    scheduler.start()
    try:
        # The immediate-check task is scheduled via asyncio.create_task,
        # which doesn't run until the event loop yields -- and check()'s own
        # DB I/O (via aiosqlite's background-thread wrapper in tests) needs
        # more than a bare no-op yield to actually complete, hence a short
        # real sleep in a retry loop rather than depending on real time
        # equal to check_interval_seconds itself.
        for _ in range(50):
            if calls:
                break
            await asyncio.sleep(0.05)
        assert len(calls) == 1
    finally:
        await scheduler.stop()
