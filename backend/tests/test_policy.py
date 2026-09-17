"""GET /api/policy -- the read-only data-policy surface (Faza 6.4)."""

from httpx import AsyncClient

from app.api.routes import policy as policy_module
from app.core.config import Settings


async def test_policy_reports_retention_and_collected_fields(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    # Explicit settings (not the ambient default/`.env`) so this asserts
    # exactly what the route derives from them, deterministically.
    monkeypatch.setattr(
        policy_module,
        "get_settings",
        lambda: Settings(
            RETENTION_DAYS_RAW_EVENTS=30,
            RETENTION_DAYS_AGGREGATES=400,
            ARCHIVE_ENABLED=True,
            ARCHIVE_ENCRYPTION_KEY=None,
            DATA_PROCESSING_PURPOSE=None,
            DATA_CONTROLLER=None,
        ),
    )
    r = await app_client.get("/api/policy", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["retention"]["raw_events_days"] == 30
    assert body["retention"]["aggregates_days"] == 400
    assert body["archiving"]["enabled"] is True
    assert body["archiving"]["encrypted"] is False
    names = {f["name"] for f in body["collected_fields"]}
    assert {"client IP", "username", "URL / domain"} <= names
    assert body["purpose"] is None
    assert body["controller"] is None


async def test_policy_reports_configured_purpose_and_encryption(
    app_client: AsyncClient, admin_token, auth_headers, monkeypatch
):
    monkeypatch.setattr(
        policy_module,
        "get_settings",
        lambda: Settings(
            DATA_PROCESSING_PURPOSE="Acceptable-use enforcement and incident investigation",
            DATA_CONTROLLER="IT Security",
            ARCHIVE_ENCRYPTION_KEY="not-a-real-fernet-key-just-a-presence-check",
        ),
    )
    r = await app_client.get("/api/policy", headers=auth_headers(admin_token))
    body = r.json()
    assert body["purpose"] == "Acceptable-use enforcement and incident investigation"
    assert body["controller"] == "IT Security"
    assert body["archiving"]["encrypted"] is True


async def test_policy_is_visible_to_an_auditor_but_not_a_viewer(
    app_client: AsyncClient, auditor_token, viewer_token, auth_headers
):
    assert (await app_client.get("/api/policy", headers=auth_headers(auditor_token))).status_code == 200
    assert (await app_client.get("/api/policy", headers=auth_headers(viewer_token))).status_code == 403


async def test_policy_requires_auth(app_client: AsyncClient):
    assert (await app_client.get("/api/policy")).status_code == 401
