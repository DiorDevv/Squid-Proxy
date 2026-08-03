"""Tests for the admin-tunable alert settings API
(app/services/alert_settings_service.py, api/routes/alert_settings.py)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service


async def test_get_settings_row_returns_defaults_when_none_configured(db_session: AsyncSession):
    row = await alert_settings_service.get_settings_row(db_session)
    assert row.sensitive_categories == ""
    assert row.non_work_minutes_threshold == alert_settings_service.DEFAULT_NON_WORK_MINUTES_THRESHOLD
    assert row.client_daily_byte_quota_bytes is None
    assert row.uncategorized_domain_request_threshold is None


async def test_update_settings_persists_and_reads_back(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session,
        [DomainCategoryLabel.GAMBLING, DomainCategoryLabel.GAMING],
        non_work_minutes_threshold=90,
        client_daily_byte_quota_bytes=10_000_000_000,
        actor_user_id="actor-1",
        uncategorized_domain_request_threshold=500,
    )

    row = await alert_settings_service.get_settings_row(db_session)
    assert alert_settings_service.parse_sensitive_categories(row.sensitive_categories) == {
        DomainCategoryLabel.GAMBLING,
        DomainCategoryLabel.GAMING,
    }
    assert row.non_work_minutes_threshold == 90
    assert row.client_daily_byte_quota_bytes == 10_000_000_000
    assert row.uncategorized_domain_request_threshold == 500


async def test_update_settings_records_audit_entry(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session,
        [DomainCategoryLabel.GAMBLING],
        non_work_minutes_threshold=90,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
        branch="filiallar",
    )

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.ALERT_SETTINGS_UPDATED)
        )
    ).scalar_one()
    assert entry.actor_user_id == "actor-1"
    assert "filiallar" in entry.detail


async def test_parse_sensitive_categories_ignores_garbage_tokens():
    parsed = alert_settings_service.parse_sensitive_categories("gambling, not-a-real-category ,gaming")
    assert parsed == {DomainCategoryLabel.GAMBLING, DomainCategoryLabel.GAMING}


async def test_alert_settings_route_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/alert-settings", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_alert_settings_get_defaults_via_api(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/alert-settings", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["sensitive_categories"] == []
    assert body["client_daily_byte_quota_bytes"] is None
    assert body["uncategorized_domain_request_threshold"] is None


async def test_alert_settings_put_and_get_via_api(app_client: AsyncClient, admin_token, auth_headers):
    put_response = await app_client.put(
        "/api/alert-settings",
        headers=auth_headers(admin_token),
        json={
            "sensitive_categories": ["gambling", "video_streaming"],
            "non_work_minutes_threshold": 45,
            "client_daily_byte_quota_bytes": 5_000_000_000,
            "uncategorized_domain_request_threshold": 200,
        },
    )
    assert put_response.status_code == 200
    body = put_response.json()
    assert set(body["sensitive_categories"]) == {"gambling", "video_streaming"}
    assert body["non_work_minutes_threshold"] == 45
    assert body["client_daily_byte_quota_bytes"] == 5_000_000_000
    assert body["uncategorized_domain_request_threshold"] == 200

    get_response = await app_client.get("/api/alert-settings", headers=auth_headers(admin_token))
    assert set(get_response.json()["sensitive_categories"]) == {"gambling", "video_streaming"}
