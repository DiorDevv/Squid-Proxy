"""Read-access audit trail (docs/PRODUCT.md #1): viewing a subject's
activity, running a targeted event search, and opening a per-actor
analytics drill-down are each recorded in audit_log_entries. Plus the
auditor role's access boundary.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry


async def _entries(session: AsyncSession, action: AuditAction) -> list[AuditLogEntry]:
    rows = await session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action))
    return list(rows.scalars().all())


async def test_viewing_client_activity_is_audited_once_per_window(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    h = auth_headers(admin_token)
    for _ in range(3):  # paging / re-open -> still one entry (dedup window)
        r = await app_client.get("/api/clients/10.0.0.9/activity", headers=h)
        assert r.status_code == 200

    entries = await _entries(db_session, AuditAction.CLIENT_ACTIVITY_VIEWED)
    assert len(entries) == 1
    assert entries[0].detail == "client_ip=10.0.0.9"
    assert entries[0].actor_email == "admin@example.com"


async def test_targeted_event_search_is_audited_but_a_bare_browse_is_not(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    h = auth_headers(admin_token)
    assert (await app_client.get("/api/events", headers=h)).status_code == 200  # bare browse
    assert (await app_client.get("/api/events", params={"search": "dropbox"}, headers=h)).status_code == 200
    assert (await app_client.get("/api/events", params={"user": "alice"}, headers=h)).status_code == 200

    entries = await _entries(db_session, AuditAction.EVENT_SEARCH_RUN)
    details = sorted(e.detail for e in entries)
    assert details == ["search=dropbox", "user=alice"]


async def test_viewing_an_analytics_actor_is_audited(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    r = await app_client.get(
        "/api/analytics/actor-detail", params={"actor": "bob", "is_user": True}, headers=auth_headers(admin_token)
    )
    assert r.status_code == 200
    entries = await _entries(db_session, AuditAction.ANALYTICS_ACTOR_VIEWED)
    assert [e.detail for e in entries] == ["user=bob"]


async def test_auditor_can_read_the_audit_log_and_data_but_cannot_mutate(
    app_client: AsyncClient, auditor_token, auth_headers
):
    h = auth_headers(auditor_token)
    # Audit log: admin-only before, now open to the auditor.
    assert (await app_client.get("/api/audit-log", headers=h)).status_code == 200
    # Ordinary read access, same as a viewer.
    assert (await app_client.get("/api/summary", headers=h)).status_code == 200
    assert (await app_client.get("/api/clients/10.0.0.1/activity", headers=h)).status_code == 200
    # No mutations.
    assert (
        await app_client.post(
            "/api/users",
            json={"email": "x@y.z", "password": "longenough1", "role": "viewer", "branch": None},
            headers=h,
        )
    ).status_code == 403
    assert (await app_client.get("/api/export", headers=h)).status_code == 403


async def test_auditor_reading_client_activity_is_itself_audited(
    app_client: AsyncClient, auditor_token, auth_headers, db_session: AsyncSession
):
    r = await app_client.get("/api/clients/10.0.0.2/activity", headers=auth_headers(auditor_token))
    assert r.status_code == 200
    entries = await _entries(db_session, AuditAction.CLIENT_ACTIVITY_VIEWED)
    assert any(e.actor_email == "auditor@example.com" and e.detail == "client_ip=10.0.0.2" for e in entries)
