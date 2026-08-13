"""API-level tests for /api/reports (api/routes/reports.py)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import reports as reports_module
from app.core.config import Settings
from app.models.audit_log import AuditAction, AuditLogEntry


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


async def test_send_report_now_records_audit_entry(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        reports_module,
        "get_settings",
        lambda: Settings(
            REPORT_RECIPIENTS=["ops@example.com"],
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_ADDRESS="squid-watch@example.com",
        ),
    )

    async def _fake_generate_and_send_report(db, since, until, branch):
        return None

    monkeypatch.setattr(reports_module, "generate_and_send_report", _fake_generate_and_send_report)

    response = await app_client.post(
        "/api/reports/send-now?branch=filiallar", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.REPORT_SENT_NOW)
        )
    ).scalar_one()
    assert "filiallar" in entry.detail


async def test_branch_admin_cannot_send_report_for_other_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    """`branch` used to be a plain unchecked Query param here, letting any
    branch-scoped admin force-send another branch's report."""
    monkeypatch.setattr(
        reports_module,
        "get_settings",
        lambda: Settings(
            REPORT_RECIPIENTS=["ops@example.com"],
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_ADDRESS="squid-watch@example.com",
        ),
    )

    response = await app_client.post(
        "/api/reports/send-now?branch=branch-b", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403
