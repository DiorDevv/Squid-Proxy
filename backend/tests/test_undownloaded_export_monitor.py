"""Tests for the undownloaded-export-job monitor
(app/services/undownloaded_export_monitor.py). Mirrors
test_uncategorized_domain_monitor.py's pattern."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_event import AnomalyEvent
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.export_settings import ExportCleanupMode
from app.services import export_settings_service
from app.services.undownloaded_export_monitor import ANOMALY_TITLE, UndownloadedExportMonitorJob


def _job(
    *,
    status: ExportJobStatus = ExportJobStatus.DONE,
    created_at: datetime,
    downloaded_at: datetime | None = None,
    branch: str | None = "default",
) -> ExportJob:
    return ExportJob(
        status=status,
        format="csv",
        since=created_at - timedelta(hours=1),
        until=created_at,
        branch=branch,
        created_at=created_at,
        completed_at=created_at,
        downloaded_at=downloaded_at,
    )


def _patch_session(monkeypatch, db_session: AsyncSession) -> None:
    import app.services.undownloaded_export_monitor as module

    monkeypatch.setattr(module, "AsyncSessionLocal", lambda: db_session)


async def _anomalies(db_session: AsyncSession) -> list[AnomalyEvent]:
    return (
        (await db_session.execute(select(AnomalyEvent).where(AnomalyEvent.title == ANOMALY_TITLE)))
        .scalars()
        .all()
    )


async def test_check_flags_job_over_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=6, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    job = _job(created_at=now - timedelta(hours=10))
    db_session.add(job)
    await db_session.commit()

    await UndownloadedExportMonitorJob().run()

    anomalies = await _anomalies(db_session)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "export_not_downloaded"
    assert anomalies[0].params == {
        "jobId": job.id,
        "format": "csv",
        "since": job.since.isoformat(),
        "until": job.until.isoformat(),
        "ageHours": 10,
        "thresholdHours": 6,
    }


async def test_check_does_not_flag_job_under_threshold(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=12, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    db_session.add(_job(created_at=now - timedelta(hours=2)))
    await db_session.commit()

    await UndownloadedExportMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_is_noop_when_warn_hours_not_configured(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=None, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    db_session.add(_job(created_at=now - timedelta(days=30)))
    await db_session.commit()

    await UndownloadedExportMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_does_not_flag_downloaded_job(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=6, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    db_session.add(_job(created_at=now - timedelta(hours=10), downloaded_at=now - timedelta(hours=9)))
    await db_session.commit()

    await UndownloadedExportMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_does_not_flag_non_done_job(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=6, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    db_session.add(_job(status=ExportJobStatus.FAILED, created_at=now - timedelta(hours=10)))
    await db_session.commit()

    await UndownloadedExportMonitorJob().run()

    assert await _anomalies(db_session) == []


async def test_check_does_not_re_flag_within_cooldown(db_session: AsyncSession, monkeypatch):
    _patch_session(monkeypatch, db_session)
    await export_settings_service.update_settings(
        db_session, ExportCleanupMode.TIME_BASED, retention_hours=48, warn_undownloaded_after_hours=6, actor_user_id="actor-1"
    )
    now = datetime.now(UTC)
    db_session.add(_job(created_at=now - timedelta(hours=10)))
    await db_session.commit()

    job = UndownloadedExportMonitorJob()
    await job.run()
    await job.run()  # simulates the next check interval while still undownloaded

    assert len(await _anomalies(db_session)) == 1
