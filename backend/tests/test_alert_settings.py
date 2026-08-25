"""Tests for the admin-tunable alert settings API
(app/services/alert_settings_service.py, api/routes/alert_settings.py)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service, telegram_alerting


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


async def test_update_settings_persists_telegram_chat_id(db_session: AsyncSession):
    await alert_settings_service.update_settings(
        db_session,
        [],
        non_work_minutes_threshold=90,
        client_daily_byte_quota_bytes=None,
        actor_user_id="actor-1",
        telegram_chat_id="-100123456",
    )

    row = await alert_settings_service.get_settings_row(db_session)
    assert row.telegram_chat_id == "-100123456"


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
    assert body["telegram_chat_id"] is None


async def test_alert_settings_put_and_get_via_api(app_client: AsyncClient, admin_token, auth_headers):
    put_response = await app_client.put(
        "/api/alert-settings",
        headers=auth_headers(admin_token),
        json={
            "sensitive_categories": ["gambling", "video_streaming"],
            "non_work_minutes_threshold": 45,
            "client_daily_byte_quota_bytes": 5_000_000_000,
            "uncategorized_domain_request_threshold": 200,
            "telegram_chat_id": "-100987654",
        },
    )
    assert put_response.status_code == 200
    body = put_response.json()
    assert set(body["sensitive_categories"]) == {"gambling", "video_streaming"}
    assert body["non_work_minutes_threshold"] == 45
    assert body["client_daily_byte_quota_bytes"] == 5_000_000_000
    assert body["uncategorized_domain_request_threshold"] == 200
    assert body["telegram_chat_id"] == "-100987654"

    get_response = await app_client.get("/api/alert-settings", headers=auth_headers(admin_token))
    assert set(get_response.json()["sensitive_categories"]) == {"gambling", "video_streaming"}
    assert get_response.json()["telegram_chat_id"] == "-100987654"


# --- Telegram test-message endpoint: sends against whatever chat id is
# given in the request body, independent of what's saved, so an admin can
# verify a chat id before persisting it. ---


async def test_telegram_test_route_requires_bot_token_configured(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    from app.api.routes import alert_settings as alert_settings_route

    monkeypatch.setattr(alert_settings_route, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN=None))

    response = await app_client.post(
        "/api/alert-settings/test-telegram",
        headers=auth_headers(admin_token),
        json={"telegram_chat_id": "-100123"},
    )
    assert response.status_code == 400


async def test_telegram_test_route_sends_message(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    from app.api.routes import alert_settings as alert_settings_route

    monkeypatch.setattr(
        alert_settings_route, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN="bot-token")
    )
    sent: list[tuple[str, str, str]] = []

    async def _fake_send_message(bot_token: str, chat_id: str, text: str) -> None:
        sent.append((bot_token, chat_id, text))

    monkeypatch.setattr(telegram_alerting, "send_message", _fake_send_message)

    response = await app_client.post(
        "/api/alert-settings/test-telegram",
        headers=auth_headers(admin_token),
        json={"telegram_chat_id": "-100123"},
    )
    assert response.status_code == 204
    assert len(sent) == 1
    assert sent[0][1] == "-100123"


async def test_telegram_test_route_returns_502_on_delivery_failure(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    from app.api.routes import alert_settings as alert_settings_route

    monkeypatch.setattr(
        alert_settings_route, "get_settings", lambda: Settings(TELEGRAM_BOT_TOKEN="bot-token")
    )

    async def _failing_send_message(bot_token: str, chat_id: str, text: str) -> None:
        raise RuntimeError("bad chat id")

    monkeypatch.setattr(telegram_alerting, "send_message", _failing_send_message)

    response = await app_client.post(
        "/api/alert-settings/test-telegram",
        headers=auth_headers(admin_token),
        json={"telegram_chat_id": "-100123"},
    )
    assert response.status_code == 502


# --- Branch scoping: previously `branch` was a plain unchecked Query param
# here, letting any branch-scoped admin read or overwrite another branch's
# alert thresholds. ---


async def test_branch_admin_get_alert_settings_defaults_to_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.get("/api/alert-settings", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    assert response.json()["branch"] == "branch-a"


async def test_branch_admin_cannot_read_other_branch_alert_settings(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.get(
        "/api/alert-settings", params={"branch": "branch-b"}, headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_overwrite_other_branch_alert_settings(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, admin_token
):
    put_response = await app_client.put(
        "/api/alert-settings",
        params={"branch": "branch-b"},
        headers=auth_headers(branch_a_admin_token),
        json={
            "sensitive_categories": ["gambling"],
            "non_work_minutes_threshold": 1,
            "client_daily_byte_quota_bytes": None,
            "uncategorized_domain_request_threshold": None,
        },
    )
    assert put_response.status_code == 403

    # branch-b's settings must be untouched by the rejected attempt.
    get_response = await app_client.get(
        "/api/alert-settings", params={"branch": "branch-b"}, headers=auth_headers(admin_token)
    )
    assert get_response.json()["sensitive_categories"] == []


# --- Telegram pairing-code linking (app/services/telegram_link_service.py):
# replaces manually typing a raw chat id with a short-lived 6-digit code
# redeemed in Telegram. ---


async def test_create_telegram_link_code_scoped_to_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.post(
        "/api/alert-settings/telegram-link", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["code"]) == 6
    assert body["code"].isdigit()


async def test_branch_admin_cannot_create_super_admin_telegram_link_code(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.post(
        "/api/alert-settings/telegram-link/super-admin", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403


async def test_unrestricted_admin_can_create_super_admin_telegram_link_code(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.post(
        "/api/alert-settings/telegram-link/super-admin", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json()["code"].isdigit()


async def test_branch_admin_cannot_view_super_admin_telegram_chat(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.get(
        "/api/alert-settings/telegram-super-admin", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403


async def test_unrestricted_admin_can_view_super_admin_telegram_chat(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/alert-settings/telegram-super-admin", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json() == {"chat_id": None}


async def test_telegram_link_status_reports_pending_code(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    create_response = await app_client.post(
        "/api/alert-settings/telegram-link", headers=auth_headers(branch_a_admin_token)
    )
    code = create_response.json()["code"]

    status_response = await app_client.get(
        f"/api/alert-settings/telegram-link/{code}/status", headers=auth_headers(branch_a_admin_token)
    )
    assert status_response.status_code == 200
    assert status_response.json() == {"consumed": False, "expired": False, "chat_id": None}


async def test_telegram_link_status_unknown_code_is_404(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/alert-settings/telegram-link/000000/status", headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


async def test_branch_admin_cannot_check_another_branchs_telegram_link_status(
    app_client: AsyncClient, branch_a_admin_token, admin_token, auth_headers
):
    create_response = await app_client.post(
        "/api/alert-settings/telegram-link",
        params={"branch": "branch-b"},
        headers=auth_headers(admin_token),
    )
    code = create_response.json()["code"]

    response = await app_client.get(
        f"/api/alert-settings/telegram-link/{code}/status", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_check_super_admin_telegram_link_status(
    app_client: AsyncClient, branch_a_admin_token, admin_token, auth_headers
):
    create_response = await app_client.post(
        "/api/alert-settings/telegram-link/super-admin", headers=auth_headers(admin_token)
    )
    code = create_response.json()["code"]

    response = await app_client.get(
        f"/api/alert-settings/telegram-link/{code}/status", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403
