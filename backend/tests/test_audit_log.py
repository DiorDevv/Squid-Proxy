"""Tests for the audit trail written by app/services/user_service.py
(app/services/audit_service.py) and read back via GET /api/audit-log."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.user import User, UserRole
from app.services import user_service


async def _seed_user(session: AsyncSession, user_id: str, email: str, role: UserRole) -> User:
    user = User(id=user_id, email=email, hashed_password="unused", role=role)
    session.add(user)
    await session.commit()
    return user


async def test_create_user_writes_audit_entry(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-1", "actor1@example.com", UserRole.ADMIN)

    await user_service.create_user(
        db_session, "created@example.com", "supersecret1", UserRole.VIEWER, actor.id
    )

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.USER_CREATED)
        )
    ).scalar_one()
    assert entry.actor_email == "actor1@example.com"
    assert entry.target_email == "created@example.com"


async def test_update_role_writes_audit_entry_with_old_and_new_role(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-2", "actor2@example.com", UserRole.ADMIN)
    target = await _seed_user(db_session, "target-2", "target2@example.com", UserRole.VIEWER)

    await user_service.update_role(db_session, target.id, UserRole.ADMIN, actor.id)

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.USER_ROLE_CHANGED)
        )
    ).scalar_one()
    assert entry.target_email == "target2@example.com"
    assert entry.detail == "viewer -> admin"


async def test_reset_password_writes_audit_entry(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-3", "actor3@example.com", UserRole.ADMIN)
    target = await _seed_user(db_session, "target-3", "target3@example.com", UserRole.VIEWER)

    await user_service.reset_password(db_session, target.id, "brand-new-password-1", actor.id)

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.USER_PASSWORD_RESET)
        )
    ).scalar_one()
    assert entry.target_email == "target3@example.com"


async def test_delete_user_writes_audit_entry_surviving_the_deleted_row(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-4", "actor4@example.com", UserRole.ADMIN)
    target = await _seed_user(db_session, "target-4", "target4@example.com", UserRole.VIEWER)

    await user_service.delete_user(db_session, target.id, actor.id)

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.USER_DELETED)
        )
    ).scalar_one()
    assert entry.target_email == "target4@example.com"

    remaining = (await db_session.execute(select(User).where(User.id == target.id))).scalar_one_or_none()
    assert remaining is None


async def test_audit_log_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/audit-log", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_audit_log_lists_recent_actions(app_client: AsyncClient, admin_token, auth_headers):
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "audited@example.com", "password": "supersecret1", "role": "viewer"},
    )
    assert create_response.status_code == 201

    response = await app_client.get("/api/audit-log", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["action"] == "user_created"
    assert body["items"][0]["target_email"] == "audited@example.com"
    assert body["total"] >= 1
