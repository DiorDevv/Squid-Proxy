"""GET /api/system-health -- the Settings -> System health snapshot."""

import json
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.system_event import SystemEvent


async def _seed(db: AsyncSession) -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    db.add_all(
        [
            RawEvent(
                timestamp=now - timedelta(hours=1),
                client_ip="10.0.0.1",
                branch="default",
                method="GET",
                url="http://x/",
                domain="x",
                action="TCP_MISS",
                status_code=200,
                bytes=100,
                duration_ms=5,
                blocked=False,
            ),
            RawEvent(
                timestamp=now - timedelta(days=30),
                client_ip="10.0.0.2",
                branch="default",
                method="GET",
                url="http://y/",
                domain="y",
                action="TCP_MISS",
                status_code=200,
                bytes=100,
                duration_ms=5,
                blocked=False,
            ),
            MinuteAggregate(
                bucket_ts=now - timedelta(minutes=2), branch="default", total_requests=2, allowed_requests=2
            ),
            SystemEvent(source="backup", message="a backup failed once", created_at=now - timedelta(hours=3)),
        ]
    )
    await db.commit()


async def test_requires_admin_or_auditor(app_client: AsyncClient, viewer_token, auth_headers):
    r = await app_client.get("/api/system-health", headers=auth_headers(viewer_token))
    assert r.status_code == 403


async def test_snapshot_shape(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession, test_app
):
    await _seed(db_session)

    class _FakeJob:
        job_name = "retention-job"
        is_alive = True
        last_run_at = datetime.now(UTC)
        last_error = None
        last_error_at = None
        consecutive_failures = 0

    test_app.state.background_jobs = {"retention-job": _FakeJob()}

    r = await app_client.get("/api/system-health", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()

    assert body["database"]["raw_events_row_count"] == 2
    assert body["database"]["raw_events_added_24h"] == 1  # only the 1h-old row
    assert body["database"]["dialect"] in ("sqlite", "postgresql")

    branches = {b["branch"]: b for b in body["ingestion"]["branches"]}
    assert "default" in branches
    assert branches["default"]["last_event_at"] is not None

    names = {j["name"] for j in body["background_jobs"]}
    assert "retention-job" in names
    assert all("consecutive_failures" in j for j in body["background_jobs"])

    assert [e["source"] for e in body["recent_events"]] == ["backup"]
    # No JOB_STATUS_DIR configured in tests -> no backup/offsite panels.
    assert body["backup"] is None and body["offsite"] is None


async def test_auditor_can_read(app_client: AsyncClient, auditor_token, auth_headers):
    r = await app_client.get("/api/system-health", headers=auth_headers(auditor_token))
    assert r.status_code == 200


async def test_backup_status_read_from_file_and_flagged_stale(
    app_client: AsyncClient, admin_token, auth_headers, tmp_path, monkeypatch
):
    from app.core.config import Settings
    from app.services import system_health_service

    (tmp_path / "backup.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-09-01T06:00:00Z",
                "ok": True,
                "last_success_at": "2026-09-01T06:00:00Z",  # weeks ago -> stale
                "last_dump": "squid-dashboard-backup-20260901T060000Z.dump",
                "last_dump_bytes": 12345,
                "consecutive_failures": 0,
                "error": None,
                "disk_total_bytes": 1000,
                "disk_free_bytes": 400,
            }
        )
    )
    monkeypatch.setattr(
        system_health_service,
        "get_settings",
        lambda: Settings(JOB_STATUS_DIR=str(tmp_path), SYSTEM_HEALTH_BACKUP_STALE_HOURS=26),
    )

    r = await app_client.get("/api/system-health", headers=auth_headers(admin_token))
    body = r.json()
    assert body["backup"]["last_dump"] == "squid-dashboard-backup-20260901T060000Z.dump"
    assert body["backup"]["disk_free_bytes"] == 400
    assert body["backup"]["stale"] is True
