"""API-level tests for /api/reports (api/routes/reports.py)."""

from httpx import AsyncClient


async def test_reports_status_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/reports/status", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_reports_status_reflects_disabled_defaults(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/reports/status", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["schedule"] == "disabled"
    assert body["recipients_configured"] is False
    assert body["last_sent_at"] is None


async def test_send_report_now_requires_configuration(app_client: AsyncClient, admin_token, auth_headers):
    """Without REPORT_RECIPIENTS/SMTP configured (the test environment's
    default), send-now must fail clearly rather than silently doing
    nothing or crashing."""
    response = await app_client.post("/api/reports/send-now", headers=auth_headers(admin_token))
    assert response.status_code == 400


async def test_send_report_now_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.post("/api/reports/send-now", headers=auth_headers(viewer_token))
    assert response.status_code == 403
