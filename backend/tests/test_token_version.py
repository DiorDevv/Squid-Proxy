"""M2: an access token stops working the moment the account's
token_version moves past it -- a role change, a branch change, or a
password reset all bump it, so a demote/deprovision takes effect on the
next request instead of lingering for the full ACCESS_TOKEN_EXPIRE_MINUTES
window. A pre-token_version token (tv=None) is grandfathered."""

import jwt
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User, UserRole


async def _make_user(db: AsyncSession, email: str, role: UserRole = UserRole.VIEWER) -> User:
    from app.core.security import hash_password

    user = User(email=email, hashed_password=hash_password("pw-123456789"), role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_token_carries_tv_claim(app_client: AsyncClient):
    resp = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    token = resp.json()["access_token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["tv"] == 1


async def test_password_reset_invalidates_existing_access_token(
    app_client: AsyncClient, admin_token: str, auth_headers, db_session: AsyncSession
):
    target = await _make_user(db_session, "reset-me@example.com")

    login = await app_client.post(
        "/api/auth/login", json={"email": "reset-me@example.com", "password": "pw-123456789"}
    )
    victim_token = login.json()["access_token"]
    # Works before the reset.
    assert (await app_client.get("/api/summary", headers=auth_headers(victim_token))).status_code == 200

    r = await app_client.post(
        f"/api/users/{target.id}/reset-password",
        headers=auth_headers(admin_token),
        json={"new_password": "brand-new-pw-123"},
    )
    assert r.status_code == 204

    # Same token, now rejected -- token_version moved past it.
    assert (await app_client.get("/api/summary", headers=auth_headers(victim_token))).status_code == 401


async def test_role_change_invalidates_existing_access_token(
    app_client: AsyncClient, admin_token: str, auth_headers, db_session: AsyncSession
):
    target = await _make_user(db_session, "promote-me@example.com", role=UserRole.VIEWER)
    login = await app_client.post(
        "/api/auth/login", json={"email": "promote-me@example.com", "password": "pw-123456789"}
    )
    old_token = login.json()["access_token"]

    r = await app_client.patch(
        f"/api/users/{target.id}/role",
        headers=auth_headers(admin_token),
        json={"role": "admin"},
    )
    assert r.status_code == 200

    assert (await app_client.get("/api/summary", headers=auth_headers(old_token))).status_code == 401
    # A fresh login reflects the new role and works.
    relogin = await app_client.post(
        "/api/auth/login", json={"email": "promote-me@example.com", "password": "pw-123456789"}
    )
    assert relogin.json()["role"] == "admin"


async def test_token_with_stale_tv_is_rejected(
    app_client: AsyncClient, auth_headers, db_session: AsyncSession
):
    """The core check, isolated: any bump to the row's token_version (a
    branch change goes through the same `user.token_version += 1` path as
    role/reset) leaves an already-issued token's tv behind, and it's
    refused on the next request."""
    user = await _make_user(db_session, "stale-tv@example.com")
    login = await app_client.post(
        "/api/auth/login", json={"email": "stale-tv@example.com", "password": "pw-123456789"}
    )
    old_token = login.json()["access_token"]
    assert (await app_client.get("/api/summary", headers=auth_headers(old_token))).status_code == 200

    row = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    row.token_version += 1
    await db_session.commit()

    assert (await app_client.get("/api/summary", headers=auth_headers(old_token))).status_code == 401


async def test_deleted_user_token_is_rejected_immediately(
    app_client: AsyncClient, admin_token: str, auth_headers, db_session: AsyncSession
):
    target = await _make_user(db_session, "delete-me@example.com")
    login = await app_client.post(
        "/api/auth/login", json={"email": "delete-me@example.com", "password": "pw-123456789"}
    )
    token = login.json()["access_token"]
    assert (await app_client.get("/api/summary", headers=auth_headers(token))).status_code == 200

    r = await app_client.delete(f"/api/users/{target.id}", headers=auth_headers(admin_token))
    assert r.status_code == 204
    assert (await app_client.get("/api/summary", headers=auth_headers(token))).status_code == 401


async def test_pre_token_version_token_is_grandfathered(
    app_client: AsyncClient, auth_headers, db_session: AsyncSession
):
    """A token minted before the column existed has no tv claim -- still
    honoured as long as the user exists (it ages out within one token
    lifetime anyway)."""
    user = await _make_user(db_session, "legacy@example.com")
    legacy_token = create_access_token(user_id=user.id, role="viewer", branch=None)  # no token_version
    claims = jwt.decode(legacy_token, options={"verify_signature": False})
    assert claims["tv"] is None

    assert (await app_client.get("/api/summary", headers=auth_headers(legacy_token))).status_code == 200
