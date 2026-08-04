"""Tests for single-branch RBAC scoping: User.branch, api/deps.py's
resolve_branch dependency, and its effect on data-read routes + GET
/api/branches. Uses a real login (not a hand-built JWT) so the whole chain
-- User.branch -> access token claim -> CurrentUser.branch -> resolve_branch
-- is exercised end to end, the same way admin_token/viewer_token already
do for role."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole


async def _scoped_viewer_token(
    app_client: AsyncClient,
    db_session: AsyncSession,
    branch: str | None,
    email: str = "scoped@example.com",
) -> str:
    db_session.add(
        User(
            email=email,
            hashed_password=hash_password("scoped-pass-123"),
            role=UserRole.VIEWER,
            branch=branch,
        )
    )
    await db_session.commit()
    response = await app_client.post(
        "/api/auth/login", json={"email": email, "password": "scoped-pass-123"}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_login_response_includes_branch(app_client: AsyncClient, db_session: AsyncSession):
    db_session.add(
        User(
            email="branch-in-response@example.com",
            hashed_password=hash_password("scoped-pass-123"),
            role=UserRole.VIEWER,
            branch="default",
        )
    )
    await db_session.commit()
    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "branch-in-response@example.com", "password": "scoped-pass-123"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["branch"] == "default"


async def test_unrestricted_admin_can_request_any_branch(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/events/recent?branch=default", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200


async def test_scoped_user_omitting_branch_gets_their_own(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _scoped_viewer_token(app_client, db_session, branch="default")
    response = await app_client.get("/api/events/recent", headers=auth_headers(token))
    assert response.status_code == 200


async def test_scoped_user_requesting_own_branch_succeeds(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _scoped_viewer_token(app_client, db_session, branch="default")
    response = await app_client.get(
        "/api/events/recent?branch=default", headers=auth_headers(token)
    )
    assert response.status_code == 200


async def test_scoped_user_requesting_a_different_branch_is_forbidden(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _scoped_viewer_token(app_client, db_session, branch="default")
    response = await app_client.get(
        "/api/events/recent?branch=some-other-branch", headers=auth_headers(token)
    )
    assert response.status_code == 403


async def test_branches_route_returns_only_the_scoped_users_branch(
    app_client: AsyncClient, db_session: AsyncSession, auth_headers
):
    token = await _scoped_viewer_token(app_client, db_session, branch="default")
    response = await app_client.get("/api/branches", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["items"] == [{"slug": "default", "label": "Default"}]


async def test_branches_route_returns_full_list_for_unrestricted_user(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get("/api/branches", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["items"] == [{"slug": "default", "label": "Default"}]


async def test_create_user_rejects_an_unknown_branch(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={
            "email": "bad-branch@example.com",
            "password": "supersecret1",
            "role": "viewer",
            "branch": "not-a-real-branch",
        },
    )
    assert response.status_code == 400


async def test_create_user_accepts_a_valid_branch(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={
            "email": "good-branch@example.com",
            "password": "supersecret1",
            "role": "viewer",
            "branch": "default",
        },
    )
    assert response.status_code == 201
    assert response.json()["branch"] == "default"


async def test_update_user_branch_route_records_audit_entry(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    from sqlalchemy import select

    from app.models.audit_log import AuditAction, AuditLogEntry

    create_response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"email": "will-be-scoped@example.com", "password": "supersecret1", "role": "viewer"},
    )
    user_id = create_response.json()["id"]

    update_response = await app_client.patch(
        f"/api/users/{user_id}/branch", headers=auth_headers(admin_token), json={"branch": "default"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["branch"] == "default"

    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.USER_BRANCH_CHANGED)
        )
    ).scalar_one()
    assert entry.target_email == "will-be-scoped@example.com"
    assert "unrestricted -> default" in entry.detail
