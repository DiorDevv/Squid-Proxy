from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


async def test_login_with_valid_credentials_returns_access_token(app_client: AsyncClient):
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["role"] == "admin"
    assert "refresh_token" in response.cookies


async def test_login_with_wrong_password_returns_401(app_client: AsyncClient):
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_protected_endpoint_without_token_returns_401(app_client: AsyncClient):
    response = await app_client.get("/api/summary")
    assert response.status_code == 401


async def test_protected_endpoint_with_valid_token_succeeds(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/summary", headers=auth_headers(admin_token))
    assert response.status_code == 200


async def test_refresh_rotates_token_and_issues_new_access_token(app_client: AsyncClient):
    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert login_response.status_code == 200

    refresh_response = await app_client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]


async def test_refresh_without_cookie_returns_401(app_client: AsyncClient):
    response = await app_client.post("/api/auth/refresh")
    assert response.status_code == 401


async def test_export_requires_admin_role(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/export", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_export_allowed_for_admin(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/export", headers=auth_headers(admin_token))
    assert response.status_code == 200


async def test_ws_ticket_requires_auth(app_client: AsyncClient):
    response = await app_client.post("/api/auth/ws-ticket")
    assert response.status_code == 401


async def test_ws_ticket_issued_for_authenticated_user(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post("/api/auth/ws-ticket", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["ticket"]


async def test_login_nonexistent_email_returns_same_status_as_wrong_password(app_client: AsyncClient):
    """Regression test for the login timing oracle: both cases must be a
    plain 401 with the same generic message, not distinguishable by the
    caller (the timing side of this is exercised by hand, not asserted here
    since wall-clock timing assertions are flaky in CI)."""
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "nobody-such-user@example.com", "password": "whatever-123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


async def test_refresh_reuse_of_rotated_token_is_rejected(app_client: AsyncClient, db_session: AsyncSession):
    """A refresh token is single-use: rotating it revokes the old row, so
    replaying the old cookie after a successful refresh must fail."""
    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert login_response.status_code == 200
    original_cookie = login_response.cookies["refresh_token"]

    # First refresh with the original cookie succeeds and rotates the
    # client's cookie jar to the new value.
    first_refresh = await app_client.post("/api/auth/refresh")
    assert first_refresh.status_code == 200

    # Replaying the now-revoked original cookie explicitly (overriding
    # whatever the jar rotated to) must be rejected.
    app_client.cookies.set("refresh_token", original_cookie)
    replayed = await app_client.post("/api/auth/refresh")
    assert replayed.status_code == 401
    assert replayed.json()["detail"] == "Invalid or expired session."


async def test_refresh_reuse_revokes_the_token_row_as_a_theft_signal(
    app_client: AsyncClient, db_session: AsyncSession
):
    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    original_cookie = login_response.cookies["refresh_token"]
    jti = original_cookie.split(".", 1)[0]

    await app_client.post("/api/auth/refresh")
    # Replay the pre-rotation cookie to trigger reuse detection.
    app_client.cookies.set("refresh_token", original_cookie)
    await app_client.post("/api/auth/refresh")

    row = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one()
    assert row.revoked is True


async def test_refresh_reuse_revokes_every_other_active_session_for_the_user(
    app_client: AsyncClient, db_session: AsyncSession
):
    """Reuse of an already-rotated refresh token is a theft signal -- every
    other still-active session for that user must be revoked too, not just
    the replayed token, since an attacker who stole and already rotated a
    token forward would otherwise keep a valid descendant token."""
    login_a = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    cookie_a = login_a.cookies["refresh_token"]

    # A second, independent session for the same user (e.g. another device).
    login_b = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    cookie_b = login_b.cookies["refresh_token"]

    # Rotate session A forward once, then replay the pre-rotation cookie to
    # trigger reuse detection.
    app_client.cookies.set("refresh_token", cookie_a)
    await app_client.post("/api/auth/refresh")
    app_client.cookies.set("refresh_token", cookie_a)
    await app_client.post("/api/auth/refresh")

    # Session B, never touched directly, must now also be revoked.
    app_client.cookies.set("refresh_token", cookie_b)
    replayed_b = await app_client.post("/api/auth/refresh")
    assert replayed_b.status_code == 401


async def test_refresh_with_garbage_cookie_returns_401(app_client: AsyncClient):
    app_client.cookies.set("refresh_token", "not-a-valid-cookie-value")
    response = await app_client.post("/api/auth/refresh")
    assert response.status_code == 401


async def test_logout_revokes_refresh_token(app_client: AsyncClient, db_session: AsyncSession):
    login_response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    cookie = login_response.cookies["refresh_token"]
    jti = cookie.split(".", 1)[0]

    logout_response = await app_client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    row = (await db_session.execute(select(RefreshToken).where(RefreshToken.jti == jti))).scalar_one()
    assert row.revoked is True
