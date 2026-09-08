"""Admin-tunable retention: GET/PUT /api/retention-settings, and the
halt-purge-if-archiving-is-behind guard in RetentionJob."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.retention as retention_module
from app.core.config import Settings
from app.models.archive_run import ArchiveRun
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.raw_event import RawEvent
from app.services import retention_settings_service
from app.services.retention import RetentionJob


def _raw(ts: datetime) -> RawEvent:
    return RawEvent(
        timestamp=ts,
        client_ip="10.0.0.1",
        branch="default",
        method="GET",
        url="http://x/",
        domain="x",
        action="TCP_MISS",
        status_code=200,
        bytes=1,
        duration_ms=1,
        blocked=False,
    )


async def test_get_defaults_seed_from_env(app_client: AsyncClient, admin_token, auth_headers, monkeypatch):
    monkeypatch.setattr(
        retention_settings_service, "get_settings", lambda: Settings(RETENTION_DAYS_RAW_EVENTS=14)
    )
    r = await app_client.get("/api/retention-settings", headers=auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json() == {
        "raw_events_days": 14,
        "halt_purge_if_archive_lag_days": None,
        "updated_at": r.json()["updated_at"],
    }


async def test_put_persists_and_audits(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    r = await app_client.put(
        "/api/retention-settings",
        headers=auth_headers(admin_token),
        json={"raw_events_days": 30, "halt_purge_if_archive_lag_days": 10},
    )
    assert r.status_code == 200
    assert r.json()["raw_events_days"] == 30
    assert r.json()["halt_purge_if_archive_lag_days"] == 10

    again = await app_client.get("/api/retention-settings", headers=auth_headers(admin_token))
    assert again.json()["raw_events_days"] == 30

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RETENTION_SETTINGS_UPDATED)
        )
    ).scalar_one()
    assert "-> 30" in entry.detail and "halt_on_archive_lag=10d" in entry.detail


async def test_put_rejects_out_of_range(app_client: AsyncClient, admin_token, auth_headers):
    for bad in (
        {"raw_events_days": 0},
        {"raw_events_days": 5000},
        {"raw_events_days": 30, "halt_purge_if_archive_lag_days": 0},
    ):
        r = await app_client.put("/api/retention-settings", headers=auth_headers(admin_token), json=bad)
        assert r.status_code == 422, bad


async def test_put_requires_admin(app_client: AsyncClient, auditor_token, auth_headers):
    r = await app_client.put(
        "/api/retention-settings", headers=auth_headers(auditor_token), json={"raw_events_days": 20}
    )
    assert r.status_code == 403


async def test_retention_uses_the_db_row_not_env(db_session: AsyncSession, monkeypatch):
    now = datetime.now(UTC)
    db_session.add_all([_raw(now - timedelta(days=10)), _raw(now - timedelta(days=1))])
    await db_session.commit()
    # Env says 30, DB row says 7 -> the 10-day-old row is purged, 1-day stays.
    await retention_settings_service.update_settings(db_session, 7, None, "admin")
    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(retention_module, "get_settings", lambda: Settings(RETENTION_DAYS_RAW_EVENTS=30))

    await RetentionJob().run()

    remaining = (await db_session.execute(select(RawEvent.timestamp))).scalars().all()
    assert len(remaining) == 1


async def test_halt_purge_when_archiving_is_behind(db_session: AsyncSession, monkeypatch):
    now = datetime.now(UTC)
    db_session.add_all([_raw(now - timedelta(days=40))])  # well past any window
    # last archive covered only up to 20 days ago -> archiving is 20d behind
    db_session.add(ArchiveRun(branch="default", archived_until=now - timedelta(days=20)))
    await db_session.commit()
    await retention_settings_service.update_settings(db_session, 14, 5, "admin")  # halt if >5d behind

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(retention_module, "get_settings", lambda: Settings())
    alerts: list[tuple[str, str]] = []

    async def _capture(src, msg, **k):
        alerts.append((src, msg))

    monkeypatch.setattr(retention_module, "notify_operator_failure", _capture)

    await RetentionJob().run()

    # the old raw_events row must still be there -- purge was halted
    assert len((await db_session.execute(select(RawEvent))).scalars().all()) == 1
    assert alerts and alerts[0][0] == "retention"
    assert "halted" in alerts[0][1]


async def test_halt_does_not_trigger_when_archiving_is_current(db_session: AsyncSession, monkeypatch):
    now = datetime.now(UTC)
    db_session.add(_raw(now - timedelta(days=40)))
    db_session.add(ArchiveRun(branch="default", archived_until=now - timedelta(days=1)))
    await db_session.commit()
    await retention_settings_service.update_settings(db_session, 14, 5, "admin")

    monkeypatch.setattr(retention_module, "AsyncSessionLocal", lambda: db_session)
    monkeypatch.setattr(retention_module, "get_settings", lambda: Settings())

    await RetentionJob().run()

    assert (await db_session.execute(select(RawEvent))).scalars().all() == []  # purged normally
