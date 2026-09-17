"""M1: the audit log is a hash chain -- every entry commits to the one
before it, so any row that is altered, inserted, or removed by someone with
database access is detectable rather than silent."""

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.services import audit_service


async def _record(db: AsyncSession, actor: str, detail: str) -> None:
    await audit_service.record(
        db, action=AuditAction.ALERT_SETTINGS_UPDATED, actor_user_id=actor, detail=detail
    )
    await db.commit()


async def test_chain_is_intact_for_normally_written_entries(db_session: AsyncSession):
    for i in range(5):
        await _record(db_session, "actor-1", f"change {i}")

    result = await audit_service.verify_chain(db_session)
    assert result.ok is True
    assert result.entries_checked == 5


async def test_each_entry_links_to_its_predecessor(db_session: AsyncSession):
    await _record(db_session, "a", "first")
    await _record(db_session, "a", "second")

    rows = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.created_at))).scalars().all()
    )
    assert rows[0].prev_hash is None
    assert rows[0].entry_hash is not None
    assert rows[1].prev_hash == rows[0].entry_hash


async def test_altering_a_row_breaks_the_chain(db_session: AsyncSession):
    await _record(db_session, "a", "legit action")
    await _record(db_session, "a", "another")
    await _record(db_session, "a", "and another")

    target = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.created_at))).scalars().all()
    )[1]
    # Rewrite history without touching the hash -- exactly what a DB-level
    # tamper looks like.
    await db_session.execute(
        update(AuditLogEntry).where(AuditLogEntry.id == target.id).values(detail="covered up")
    )
    await db_session.commit()

    result = await audit_service.verify_chain(db_session)
    assert result.ok is False
    assert result.broken_at["id"] == target.id
    assert "altered" in result.broken_at["reason"]
    assert result.entries_checked == 1  # first entry still verified


async def test_deleting_a_middle_row_breaks_the_chain(db_session: AsyncSession):
    for i in range(4):
        await _record(db_session, "a", f"e{i}")
    rows = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.created_at))).scalars().all()
    )
    await db_session.execute(AuditLogEntry.__table__.delete().where(AuditLogEntry.id == rows[1].id))
    await db_session.commit()

    result = await audit_service.verify_chain(db_session)
    assert result.ok is False
    # rows[2] now points at a prev_hash whose row is gone.
    assert result.broken_at["id"] == rows[2].id
    assert "inserted or deleted" in result.broken_at["reason"]


async def test_verify_endpoint_reports_ok(
    app_client: AsyncClient, admin_token: str, auth_headers, db_session: AsyncSession
):
    await _record(db_session, "a", "something")
    r = await app_client.get("/api/audit-log/verify", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["broken_at"] is None


async def test_verify_endpoint_reports_a_break(
    app_client: AsyncClient, admin_token: str, auth_headers, db_session: AsyncSession
):
    await _record(db_session, "a", "one")
    await _record(db_session, "a", "two")
    row = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.created_at))).scalars().all()
    )[0]
    await db_session.execute(
        update(AuditLogEntry).where(AuditLogEntry.id == row.id).values(actor_email="ghost@x")
    )
    await db_session.commit()

    r = await app_client.get("/api/audit-log/verify", headers=auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_verify_endpoint_requires_admin_or_auditor(
    app_client: AsyncClient, viewer_token: str, auth_headers
):
    r = await app_client.get("/api/audit-log/verify", headers=auth_headers(viewer_token))
    assert r.status_code == 403
