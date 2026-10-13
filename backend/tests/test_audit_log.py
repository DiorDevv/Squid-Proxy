"""Tests for the audit trail written by app/services/user_service.py
(app/services/audit_service.py) and read back via GET /api/audit-log."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.user import User, UserRole
from app.services import user_service


async def _seed_user(session: AsyncSession, user_id: str, username: str, role: UserRole) -> User:
    user = User(id=user_id, username=username, hashed_password="unused", role=role)
    session.add(user)
    await session.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(user_id=user.id, role=user.role.value, branch=user.branch, username=user.username)


async def _entry(session: AsyncSession, action: AuditAction) -> AuditLogEntry:
    return (await session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action))).scalar_one()


async def test_create_user_writes_audit_entry(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-1", "actor1", UserRole.SUPERADMIN)

    await user_service.create_user(db_session, _actor(actor), username="created", role=UserRole.VIEWER)

    entry = await _entry(db_session, AuditAction.USER_CREATED)
    assert entry.actor_email == "actor1"
    assert entry.target_email == "created"


async def test_update_role_writes_audit_entry_with_old_and_new_role(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-2", "actor2", UserRole.SUPERADMIN)
    target = await _seed_user(db_session, "target-2", "target2", UserRole.VIEWER)

    await user_service.update_role(db_session, target.id, UserRole.ADMIN, _actor(actor))

    entry = await _entry(db_session, AuditAction.USER_ROLE_CHANGED)
    assert entry.target_email == "target2"
    assert entry.detail == "viewer -> admin"


async def test_reset_password_writes_audit_entry(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-3", "actor3", UserRole.SUPERADMIN)
    target = await _seed_user(db_session, "target-3", "target3", UserRole.VIEWER)

    await user_service.reset_password(db_session, target.id, _actor(actor))

    entry = await _entry(db_session, AuditAction.USER_PASSWORD_RESET)
    assert entry.target_email == "target3"


async def test_deactivate_user_writes_audit_entry_and_keeps_the_row(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-4", "actor4", UserRole.SUPERADMIN)
    target = await _seed_user(db_session, "target-4", "target4", UserRole.VIEWER)

    await user_service.set_active(db_session, target.id, False, _actor(actor))

    entry = await _entry(db_session, AuditAction.USER_DEACTIVATED)
    assert entry.target_email == "target4"
    remaining = (await db_session.execute(select(User).where(User.id == target.id))).scalar_one()
    assert remaining.is_active is False


async def test_profile_update_writes_before_and_after(db_session: AsyncSession):
    actor = await _seed_user(db_session, "actor-5", "actor5", UserRole.SUPERADMIN)
    target = await _seed_user(db_session, "target-5", "target5", UserRole.VIEWER)

    await user_service.update_profile(db_session, target.id, _actor(actor), full_name="Ali Valiyev")

    entry = await _entry(db_session, AuditAction.USER_UPDATED)
    assert entry.detail == "full_name: - -> Ali Valiyev"


async def test_audit_log_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/audit-log", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_audit_log_lists_recent_actions(app_client: AsyncClient, admin_token, auth_headers):
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "audited", "role": "viewer"},
    )
    assert create_response.status_code == 201

    response = await app_client.get("/api/audit-log", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["action"] == "user_created"
    assert body["items"][0]["target_email"] == "audited"
    assert body["total"] >= 1


async def test_branch_admin_cannot_see_other_branch_audit_entries(
    app_client: AsyncClient, admin_token, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    """GET /api/audit-log used to have no branch scoping at all -- a
    branch-a admin could read every branch's user/export/alert-settings
    history. This is the regression test for that fix (see
    api/routes/audit.py's resolve_branch dependency and
    audit_service.list_entries's branch filter). Role-change (not create,
    which validates `branch` against the configured branch list -- only
    "default" is configured in tests) is used to attach a target user to an
    arbitrary branch."""
    target = await _seed_user(db_session, "branch-b-target", "branch-b-user", UserRole.VIEWER)
    target.branch = "branch-b"
    await db_session.commit()

    role_response = await app_client.patch(
        f"/api/users/{target.id}/role", headers=auth_headers(admin_token), json={"role": "admin"}
    )
    assert role_response.status_code == 200

    response = await app_client.get("/api/audit-log", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    target_emails = [item["target_email"] for item in response.json()["items"]]
    assert "branch-b-user" not in target_emails


async def test_branch_admin_sees_own_branch_audit_entries(
    app_client: AsyncClient, admin_token, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed_user(db_session, "branch-a-target", "branch-a-user", UserRole.VIEWER)
    target.branch = "branch-a"
    await db_session.commit()

    role_response = await app_client.patch(
        f"/api/users/{target.id}/role", headers=auth_headers(admin_token), json={"role": "admin"}
    )
    assert role_response.status_code == 200

    response = await app_client.get("/api/audit-log", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    target_emails = [item["target_email"] for item in response.json()["items"]]
    assert "branch-a-user" in target_emails


async def test_branch_admin_still_sees_entries_with_no_branch(
    app_client: AsyncClient, admin_token, branch_a_admin_token, auth_headers
):
    """A domain-category change has no branch dimension at all (every admin,
    scoped or not, can set one) -- it must stay visible to a branch-scoped
    admin rather than disappearing along with genuinely other-branch
    entries."""
    set_response = await app_client.put(
        "/api/domain-categories/example.com",
        headers=auth_headers(admin_token),
        json={"category": "work_tools"},
    )
    assert set_response.status_code == 200

    response = await app_client.get("/api/audit-log", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    actions = [item["action"] for item in response.json()["items"]]
    assert "domain_category_set" in actions


async def test_branch_admin_requesting_another_branchs_audit_log_is_forbidden(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.get(
        "/api/audit-log", params={"branch": "branch-b"}, headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 403
