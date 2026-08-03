"""Tests for the admin-tunable export cleanup policy
(app/services/export_settings_service.py, api/routes/export_settings.py)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.export_settings import ExportCleanupMode
from app.services import export_settings_service


async def test_get_settings_row_returns_defaults_when_none_configured(db_session: AsyncSession):
    row = await export_settings_service.get_settings_row(db_session)
    assert row.cleanup_mode == ExportCleanupMode.TIME_BASED
    assert row.retention_hours == export_settings_service.DEFAULT_RETENTION_HOURS
    assert row.warn_undownloaded_after_hours is None


async def test_update_settings_persists_and_reads_back(db_session: AsyncSession):
    await export_settings_service.update_settings(
        db_session,
        cleanup_mode=ExportCleanupMode.AFTER_DOWNLOAD,
        retention_hours=72,
        warn_undownloaded_after_hours=12,
        actor_user_id="actor-1",
    )

    row = await export_settings_service.get_settings_row(db_session)
    assert row.cleanup_mode == ExportCleanupMode.AFTER_DOWNLOAD
    assert row.retention_hours == 72
    assert row.warn_undownloaded_after_hours == 12


async def test_update_settings_records_audit_entry(db_session: AsyncSession):
    await export_settings_service.update_settings(
        db_session,
        cleanup_mode=ExportCleanupMode.AFTER_DOWNLOAD,
        retention_hours=72,
        warn_undownloaded_after_hours=12,
        actor_user_id="actor-1",
    )

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EXPORT_SETTINGS_UPDATED)
        )
    ).scalar_one()
    assert entry.actor_user_id == "actor-1"
    assert "after_download" in entry.detail
    assert "72" in entry.detail


async def test_update_settings_on_second_call_updates_existing_row(db_session: AsyncSession):
    await export_settings_service.update_settings(
        db_session,
        ExportCleanupMode.TIME_BASED,
        retention_hours=48,
        warn_undownloaded_after_hours=None,
        actor_user_id="actor-1",
    )
    await export_settings_service.update_settings(
        db_session,
        ExportCleanupMode.TIME_BASED,
        retention_hours=24,
        warn_undownloaded_after_hours=6,
        actor_user_id="actor-1",
    )

    row = await export_settings_service.get_settings_row(db_session)
    assert row.retention_hours == 24
    assert row.warn_undownloaded_after_hours == 6


async def test_export_settings_route_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/export-settings", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_export_settings_get_defaults_via_api(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/export-settings", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["cleanup_mode"] == "time_based"
    assert body["retention_hours"] == 48
    assert body["warn_undownloaded_after_hours"] is None


async def test_export_settings_put_and_get_via_api(app_client: AsyncClient, admin_token, auth_headers):
    put_response = await app_client.put(
        "/api/export-settings",
        headers=auth_headers(admin_token),
        json={"cleanup_mode": "after_download", "retention_hours": 24, "warn_undownloaded_after_hours": 8},
    )
    assert put_response.status_code == 200
    body = put_response.json()
    assert body["cleanup_mode"] == "after_download"
    assert body["retention_hours"] == 24
    assert body["warn_undownloaded_after_hours"] == 8

    get_response = await app_client.get("/api/export-settings", headers=auth_headers(admin_token))
    assert get_response.json()["cleanup_mode"] == "after_download"


async def test_export_settings_put_rejects_non_positive_retention_hours(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.put(
        "/api/export-settings",
        headers=auth_headers(admin_token),
        json={"cleanup_mode": "time_based", "retention_hours": 0, "warn_undownloaded_after_hours": None},
    )
    assert response.status_code == 422
