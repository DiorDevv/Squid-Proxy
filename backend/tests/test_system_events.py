"""M3 groundwork: every notify_operator_failure() now also lands a durable
system_events row (so a failure isn't lost when no webhook is set), the
retention job prunes them, and IntervalJob tracks its own last error."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models.db as db_module
import app.services.retention as retention_module
from app.core.config import Settings
from app.models.system_event import SystemEvent, SystemEventSeverity
from app.services import ops_alerting
from app.services.interval_job import IntervalJob
from app.services.retention import RetentionJob


async def test_notify_operator_failure_persists_a_system_event(db_engine, monkeypatch):
    monkeypatch.setattr(
        ops_alerting, "get_settings", lambda: Settings(OPS_ALERT_WEBHOOK_URL=None, ALERT_WEBHOOK_URL=None)
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", maker)

    await ops_alerting.notify_operator_failure("backup", "Database backup command failed (exit 1)")

    async with maker() as s:
        rows = (await s.execute(select(SystemEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "backup"
    assert "backup command failed" in rows[0].message
    assert rows[0].severity is SystemEventSeverity.ERROR


async def test_notify_operator_failure_swallows_a_broken_db(monkeypatch):
    """A DB that can't be reached must not make notify_operator_failure
    raise -- the failure it's reporting is the important thing."""
    monkeypatch.setattr(
        ops_alerting, "get_settings", lambda: Settings(OPS_ALERT_WEBHOOK_URL=None, ALERT_WEBHOOK_URL=None)
    )

    class _BadSession:
        async def __aenter__(self):
            raise RuntimeError("no db")

        async def __aexit__(self, *e):
            return False

    monkeypatch.setattr("app.models.db.AsyncSessionLocal", lambda: _BadSession())
    await ops_alerting.notify_operator_failure("retention", "boom")  # must not raise


async def test_retention_prunes_old_system_events(db_session: AsyncSession, monkeypatch):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            SystemEvent(source="backup", message="old", created_at=now - timedelta(days=200)),
            SystemEvent(source="backup", message="recent", created_at=now - timedelta(days=2)),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(
        retention_module, "get_settings", lambda: Settings(RETENTION_DAYS_SYSTEM_EVENTS=90)
    )
    await RetentionJob().run()

    remaining = (await db_session.execute(select(SystemEvent.message))).scalars().all()
    assert remaining == ["recent"]


async def test_interval_job_records_last_error_and_recovers():
    calls = {"n": 0}

    class _Flaky(IntervalJob):
        job_name = "flaky-test-job"
        failure_source_tag = "flaky"
        failure_log_message = "flaky failed"

        async def run(self) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("first run boom")

    job = _Flaky(interval_seconds=1)
    assert job.last_error is None and job.consecutive_failures == 0

    await job._run_catching_errors()
    assert job.consecutive_failures == 1
    assert job.last_error is not None and "first run boom" in job.last_error
    assert job.last_error_at is not None

    await job._run_catching_errors()
    assert job.consecutive_failures == 0
    assert job.last_error is None
    assert job.last_run_at is not None
