import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LogSource, Settings
from app.core.security import hash_password
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services import user_service


async def test_list_users_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/users", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_list_users_returns_seeded_admin(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/users", headers=auth_headers(admin_token))
    assert response.status_code == 200
    emails = [u["email"] for u in response.json()]
    assert "admin@example.com" in emails


async def test_create_user_succeeds(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "new.viewer@example.com", "password": "supersecret1", "role": "viewer"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.viewer@example.com"
    assert body["role"] == "viewer"


async def test_create_user_duplicate_email_returns_409(app_client: AsyncClient, admin_token, auth_headers):
    payload = {"email": "dup@example.com", "password": "supersecret1", "role": "viewer"}
    first = await app_client.post("/api/users", headers=auth_headers(admin_token), json=payload)
    assert first.status_code == 201

    second = await app_client.post("/api/users", headers=auth_headers(admin_token), json=payload)
    assert second.status_code == 409


async def test_create_user_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(viewer_token),
        json={"email": "x@example.com", "password": "supersecret1", "role": "viewer"},
    )
    assert response.status_code == 403


async def test_update_role_changes_viewer_to_admin(app_client: AsyncClient, admin_token, auth_headers):
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "promote.me@example.com", "password": "supersecret1", "role": "viewer"},
    )
    user_id = create_response.json()["id"]

    response = await app_client.patch(
        f"/api/users/{user_id}/role", headers=auth_headers(admin_token), json={"role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_update_role_cannot_modify_self(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    admin_row = (
        await db_session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()

    response = await app_client.patch(
        f"/api/users/{admin_row.id}/role", headers=auth_headers(admin_token), json={"role": "viewer"}
    )
    assert response.status_code == 400


async def test_reset_password_allows_new_login(app_client: AsyncClient, admin_token, auth_headers):
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "reset.me@example.com", "password": "old-password-1", "role": "viewer"},
    )
    user_id = create_response.json()["id"]

    reset_response = await app_client.post(
        f"/api/users/{user_id}/reset-password",
        headers=auth_headers(admin_token),
        json={"new_password": "brand-new-password-1"},
    )
    assert reset_response.status_code == 204

    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "reset.me@example.com", "password": "brand-new-password-1"},
    )
    assert login_response.status_code == 200

    old_login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "reset.me@example.com", "password": "old-password-1"},
    )
    assert old_login_response.status_code == 401


async def test_reset_password_revokes_existing_refresh_tokens(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    """A password reset is often a response to a compromised account -- a
    refresh cookie issued before the reset must stop working, not just the
    password itself."""
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "reset.revoke.me@example.com", "password": "old-password-1", "role": "viewer"},
    )
    user_id = create_response.json()["id"]

    login_response = await app_client.post(
        "/api/auth/login", json={"email": "reset.revoke.me@example.com", "password": "old-password-1"}
    )
    assert login_response.status_code == 200
    refresh_cookie = login_response.cookies.get("refresh_token")
    assert refresh_cookie is not None

    reset_response = await app_client.post(
        f"/api/users/{user_id}/reset-password",
        headers=auth_headers(admin_token),
        json={"new_password": "brand-new-password-1"},
    )
    assert reset_response.status_code == 204

    tokens = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)))
        .scalars()
        .all()
    )
    assert len(tokens) == 1
    assert tokens[0].revoked is True

    app_client.cookies.set("refresh_token", refresh_cookie)
    refresh_response = await app_client.post("/api/auth/refresh")
    assert refresh_response.status_code == 401


async def test_delete_user_succeeds_and_revokes_refresh_tokens(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "delete.me@example.com", "password": "supersecret1", "role": "viewer"},
    )
    user_id = create_response.json()["id"]

    login_response = await app_client.post(
        "/api/auth/login", json={"email": "delete.me@example.com", "password": "supersecret1"}
    )
    assert login_response.status_code == 200
    tokens_before = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)))
        .scalars()
        .all()
    )
    assert len(tokens_before) == 1

    delete_response = await app_client.delete(f"/api/users/{user_id}", headers=auth_headers(admin_token))
    assert delete_response.status_code == 204

    remaining_user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    assert remaining_user is None
    remaining_tokens = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)))
        .scalars()
        .all()
    )
    assert remaining_tokens == []


async def test_delete_user_cannot_delete_self(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    admin_row = (
        await db_session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()

    response = await app_client.delete(f"/api/users/{admin_row.id}", headers=auth_headers(admin_token))
    assert response.status_code == 400


async def test_delete_user_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.delete("/api/users/some-id", headers=auth_headers(viewer_token))
    assert response.status_code == 403


# --- Last-admin guard: exercised directly against the service layer, which
# is far clearer than contorting the route-level self-modify guard (you
# can't demote/delete "yourself" and "the last admin" in the same call) into
# proving both guards independently through HTTP alone. ---


async def test_service_update_role_blocks_demoting_the_last_admin(db_session: AsyncSession):
    sole_admin = User(
        id="sole-admin-1", email="sole.admin1@example.com", hashed_password="unused", role=UserRole.ADMIN
    )
    other_user = User(
        id="other-actor-1", email="other.actor1@example.com", hashed_password="unused", role=UserRole.VIEWER
    )
    db_session.add_all([sole_admin, other_user])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await user_service.update_role(
            db_session, sole_admin.id, UserRole.VIEWER, current_user_id=other_user.id
        )
    assert exc_info.value.status_code == 400
    assert "last remaining admin" in exc_info.value.detail


async def test_service_delete_user_blocks_deleting_the_last_admin(db_session: AsyncSession):
    sole_admin = User(
        id="sole-admin-2", email="sole.admin2@example.com", hashed_password="unused", role=UserRole.ADMIN
    )
    other_user = User(
        id="other-actor-2", email="other.actor2@example.com", hashed_password="unused", role=UserRole.VIEWER
    )
    db_session.add_all([sole_admin, other_user])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await user_service.delete_user(db_session, sole_admin.id, current_user_id=other_user.id)
    assert exc_info.value.status_code == 400
    assert "last remaining admin" in exc_info.value.detail


async def test_service_update_role_allows_demoting_when_multiple_admins_exist(db_session: AsyncSession):
    first_admin = User(
        id="first-admin-3", email="first.admin3@example.com", hashed_password="unused", role=UserRole.ADMIN
    )
    second_admin = User(
        id="second-admin-3",
        email="second.admin3@example.com",
        hashed_password="unused",
        role=UserRole.ADMIN,
    )
    other_user = User(
        id="other-actor-3", email="other.actor3@example.com", hashed_password="unused", role=UserRole.VIEWER
    )
    db_session.add_all([first_admin, second_admin, other_user])
    await db_session.commit()

    updated = await user_service.update_role(
        db_session, second_admin.id, UserRole.VIEWER, current_user_id=other_user.id
    )
    assert updated.role == UserRole.VIEWER


# --- Branch scoping: a branch-scoped admin must only see/manage users in
# their own branch, and must never be able to grant unrestricted (branch=
# None) or another branch's access to anyone -- regression coverage for the
# IDOR/privilege-escalation gap user_service used to have no enforcement
# for at all (update_branch's old docstring incorrectly assumed branch
# "only ever narrows data visibility, never grants anything"). ---


def _multi_branch_settings() -> Settings:
    return Settings(
        LOG_SOURCES=[
            LogSource(branch="default", path="/data/default/access.log"),
            LogSource(branch="branch-a", path="/data/branch-a/access.log"),
            LogSource(branch="branch-b", path="/data/branch-b/access.log"),
        ]
    )


async def _create_branch_b_user(db_session: AsyncSession, *, email: str = "other.branch@example.com") -> User:
    other_branch_user = User(
        email=email, hashed_password=hash_password("unused-pass-123"), role=UserRole.VIEWER, branch="branch-b"
    )
    db_session.add(other_branch_user)
    await db_session.commit()
    await db_session.refresh(other_branch_user)
    return other_branch_user


async def test_branch_admin_list_users_excludes_other_branches(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    await _create_branch_b_user(db_session)

    response = await app_client.get("/api/users", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    emails = {u["email"] for u in response.json()}
    assert "branch-a-admin@example.com" in emails
    assert "other.branch@example.com" not in emails


async def test_branch_admin_create_user_defaults_to_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)

    response = await app_client.post(
        "/api/users",
        headers=auth_headers(branch_a_admin_token),
        json={"email": "new.viewer.branch-a@example.com", "password": "supersecret1", "role": "viewer"},
    )
    assert response.status_code == 201
    assert response.json()["branch"] == "branch-a"


async def test_branch_admin_cannot_create_user_in_other_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)

    response = await app_client.post(
        "/api/users",
        headers=auth_headers(branch_a_admin_token),
        json={
            "email": "sneaky@example.com",
            "password": "supersecret1",
            "role": "viewer",
            "branch": "branch-b",
        },
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_create_unrestricted_user(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    """Explicitly requesting branch=null (unrestricted) from a branch-scoped
    admin must never actually produce an unrestricted account -- it's
    silently pinned to the actor's own branch instead, the same
    substitution behavior as api.deps.resolve_branch for query params."""
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)

    response = await app_client.post(
        "/api/users",
        headers=auth_headers(branch_a_admin_token),
        json={
            "email": "wannabe.unrestricted@example.com",
            "password": "supersecret1",
            "role": "admin",
            "branch": None,
        },
    )
    assert response.status_code == 201
    assert response.json()["branch"] == "branch-a"


async def test_branch_admin_cannot_view_other_branch_user(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    other_branch_user = await _create_branch_b_user(db_session)

    response = await app_client.patch(
        f"/api/users/{other_branch_user.id}/role",
        headers=auth_headers(branch_a_admin_token),
        json={"role": "admin"},
    )
    assert response.status_code == 404


async def test_branch_admin_cannot_reset_password_of_other_branch_user(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    other_branch_user = await _create_branch_b_user(db_session)

    response = await app_client.post(
        f"/api/users/{other_branch_user.id}/reset-password",
        headers=auth_headers(branch_a_admin_token),
        json={"new_password": "brand-new-password-1"},
    )
    assert response.status_code == 404


async def test_branch_admin_cannot_delete_other_branch_user(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    other_branch_user = await _create_branch_b_user(db_session)

    response = await app_client.delete(
        f"/api/users/{other_branch_user.id}", headers=auth_headers(branch_a_admin_token)
    )
    assert response.status_code == 404


async def test_branch_admin_cannot_move_other_branch_user_into_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    other_branch_user = await _create_branch_b_user(db_session)

    response = await app_client.patch(
        f"/api/users/{other_branch_user.id}/branch",
        headers=auth_headers(branch_a_admin_token),
        json={"branch": "branch-a"},
    )
    assert response.status_code == 404


async def test_branch_admin_cannot_escalate_own_branch_to_unrestricted(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession, monkeypatch
):
    """The core privilege-escalation regression: api.deps.resolve_branch
    treats branch=None as unrestricted access to every branch's data, so a
    branch-scoped admin granting themselves branch=null would be a full
    escalation. Must be a no-op (still "branch-a"), not honored."""
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)
    admin_row = (
        await db_session.execute(select(User).where(User.email == "branch-a-admin@example.com"))
    ).scalar_one()

    response = await app_client.patch(
        f"/api/users/{admin_row.id}/branch",
        headers=auth_headers(branch_a_admin_token),
        json={"branch": None},
    )
    assert response.status_code == 200
    assert response.json()["branch"] == "branch-a"

    await db_session.refresh(admin_row)
    assert admin_row.branch == "branch-a"


async def test_branch_admin_cannot_move_own_branch_to_another_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    admin_row = (
        await db_session.execute(select(User).where(User.email == "branch-a-admin@example.com"))
    ).scalar_one()

    response = await app_client.patch(
        f"/api/users/{admin_row.id}/branch",
        headers=auth_headers(branch_a_admin_token),
        json={"branch": "branch-b"},
    )
    assert response.status_code == 403

    await db_session.refresh(admin_row)
    assert admin_row.branch == "branch-a"
