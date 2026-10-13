from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import LogSource, Settings
from app.core.password_policy import password_problems
from app.core.security import LoginThrottle, hash_password
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services import user_service

NEW_PASSWORD = "Fresh-Start-2026!x"


async def _login(client: AsyncClient, username: str, password: str) -> dict:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


async def _create(client: AsyncClient, token: str, **body) -> dict:
    response = await client.post("/api/users", headers={"Authorization": f"Bearer {token}"}, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _seed(
    db: AsyncSession,
    username: str,
    role: UserRole = UserRole.VIEWER,
    branch: str | None = None,
    password: str = "seeded-pass-123",
) -> User:
    user = User(username=username, hashed_password=hash_password(password), role=role, branch=branch)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _multi_branch_settings() -> Settings:
    return Settings(
        LOG_SOURCES=[
            LogSource(branch="default", path="/data/default/access.log"),
            LogSource(branch="branch-a", path="/data/branch-a/access.log"),
            LogSource(branch="branch-b", path="/data/branch-b/access.log"),
        ]
    )


# --- Listing -------------------------------------------------------------------


async def test_list_users_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/users", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_list_users_returns_bootstrapped_superadmin(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/users", headers=auth_headers(admin_token))
    assert response.status_code == 200
    admin = next(u for u in response.json() if u["username"] == "admin")
    assert admin["role"] == "superadmin"
    assert admin["is_active"] is True
    assert admin["active_sessions"] == 1
    assert admin["last_login_at"] is not None


# --- Creating: temporary password, first-login change ---------------------------


async def test_create_user_returns_one_time_password_meeting_policy(
    app_client: AsyncClient, admin_token, auth_headers
):
    body = await _create(
        app_client, admin_token, username="New.Viewer", full_name="Ali Valiyev", role="viewer"
    )
    assert body["user"]["username"] == "new.viewer"
    assert body["user"]["full_name"] == "Ali Valiyev"
    assert body["user"]["must_change_password"] is True
    assert body["user"]["created_by"] == "admin"
    assert password_problems(body["temporary_password"]) == []


async def test_new_user_must_change_password_before_anything_else(
    app_client: AsyncClient, admin_token, auth_headers
):
    created = await _create(app_client, admin_token, username="first.login", role="viewer")
    login = await _login(app_client, "first.login", created["temporary_password"])
    assert login["must_change_password"] is True
    headers = auth_headers(login["access_token"])

    blocked = await app_client.get("/api/summary", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password_change_required"
    assert (await app_client.get("/api/auth/me", headers=headers)).json()["must_change_password"] is True

    changed = await app_client.post(
        "/api/auth/password",
        headers=headers,
        json={"current_password": created["temporary_password"], "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    # Same token keeps working -- the gate reads the live row.
    assert (await app_client.get("/api/summary", headers=headers)).status_code == 200


async def test_create_user_duplicate_username_is_case_insensitive(
    app_client: AsyncClient, admin_token, auth_headers
):
    await _create(app_client, admin_token, username="dup", role="viewer")
    response = await app_client.post(
        "/api/users", headers=auth_headers(admin_token), json={"username": "DUP", "role": "viewer"}
    )
    assert response.status_code == 409


@pytest.mark.parametrize("username", ["ab", "-starts-with-dash", "has space", "root", "кирилл"])
async def test_create_user_rejects_invalid_usernames(
    app_client: AsyncClient, admin_token, auth_headers, username: str
):
    response = await app_client.post(
        "/api/users", headers=auth_headers(admin_token), json={"username": username, "role": "viewer"}
    )
    assert response.status_code == 400


async def test_superadmin_cannot_be_branch_scoped(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(admin_token),
        json={"username": "scoped.super", "role": "superadmin", "branch": "default"},
    )
    assert response.status_code == 400


async def test_viewer_cannot_create_user(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.post(
        "/api/users", headers=auth_headers(viewer_token), json={"username": "nope", "role": "viewer"}
    )
    assert response.status_code == 403


# --- Re-authentication ---------------------------------------------------------


async def _age_reauth(db: AsyncSession) -> None:
    await db.execute(update(RefreshToken).values(reauth_at=datetime.now(UTC) - timedelta(hours=1)))
    await db.commit()


async def test_sensitive_action_requires_recent_password_confirmation(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    await _age_reauth(db_session)
    headers = auth_headers(admin_token)

    stale = await app_client.post("/api/users", headers=headers, json={"username": "later", "role": "viewer"})
    assert stale.status_code == 403
    assert stale.json()["detail"] == "reauth_required"

    wrong = await app_client.post("/api/auth/reauth", headers=headers, json={"password": "not-it"})
    assert wrong.status_code == 400

    ok = await app_client.post(
        "/api/auth/reauth", headers=headers, json={"password": "admin-test-password-123"}
    )
    assert ok.status_code == 200
    assert ok.json()["valid_minutes"] == 10

    retried = await app_client.post(
        "/api/users", headers=headers, json={"username": "later", "role": "viewer"}
    )
    assert retried.status_code == 201


async def test_descriptive_edit_does_not_require_reauth(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "describe.me")
    await _age_reauth(db_session)

    response = await app_client.patch(
        f"/api/users/{target.id}",
        headers=auth_headers(admin_token),
        json={"full_name": "Described", "note": "IT dept", "email": "d@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["full_name"], body["note"], body["email"]) == ("Described", "IT dept", "d@example.com")


# --- Roles ---------------------------------------------------------------------


async def test_superadmin_can_promote_a_viewer(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "promote.me")
    response = await app_client.patch(
        f"/api/users/{target.id}/role", headers=auth_headers(admin_token), json={"role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_promoting_to_superadmin_clears_branch(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "rising.star", branch="default")
    response = await app_client.patch(
        f"/api/users/{target.id}/role", headers=auth_headers(admin_token), json={"role": "superadmin"}
    )
    assert response.status_code == 200
    assert response.json()["branch"] is None


async def test_cannot_change_own_role(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    admin_row = (await db_session.execute(select(User).where(User.username == "admin"))).scalar_one()
    response = await app_client.patch(
        f"/api/users/{admin_row.id}/role", headers=auth_headers(admin_token), json={"role": "viewer"}
    )
    assert response.status_code == 400


async def test_last_active_superadmin_cannot_be_demoted_or_deactivated(db_session: AsyncSession):
    """Unreachable over the API (an actor is always another active super
    admin), so exercised at the service layer with an out-of-band actor --
    the same position scripts/create_admin.py is in."""
    only = await _seed(db_session, "only.super", role=UserRole.SUPERADMIN)
    admin_row = (await db_session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
    assert admin_row is None  # db_session fixture alone has no bootstrap admin
    actor = CurrentUser(user_id="cli", role="superadmin", username="cli")

    with pytest.raises(HTTPException) as exc:
        await user_service.update_role(db_session, only.id, UserRole.ADMIN, actor)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await user_service.set_active(db_session, only.id, False, actor)
    assert exc.value.status_code == 400


async def test_superadmin_can_demote_another_superadmin(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    other = await _seed(db_session, "other.super", role=UserRole.SUPERADMIN)
    response = await app_client.patch(
        f"/api/users/{other.id}/role", headers=auth_headers(admin_token), json={"role": "auditor"}
    )
    assert response.status_code == 200


# --- Password reset ------------------------------------------------------------


async def test_reset_password_issues_new_temporary_password_and_ends_sessions(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "reset.me", password="old-password-1")
    victim = await _login(app_client, "reset.me", "old-password-1")

    response = await app_client.post(
        f"/api/users/{target.id}/reset-password", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["must_change_password"] is True
    assert body["user"]["active_sessions"] == 0

    assert (
        await app_client.get("/api/summary", headers=auth_headers(victim["access_token"]))
    ).status_code == 401
    old = await app_client.post(
        "/api/auth/login", json={"username": "reset.me", "password": "old-password-1"}
    )
    assert old.status_code == 401
    assert (await _login(app_client, "reset.me", body["temporary_password"]))["must_change_password"] is True


# --- Deactivation --------------------------------------------------------------


async def test_deactivated_user_cannot_sign_in_and_can_be_reactivated(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "leaver", password="leaver-pass-123")
    session = await _login(app_client, "leaver", "leaver-pass-123")

    off = await app_client.post(
        f"/api/users/{target.id}/active", headers=auth_headers(admin_token), json={"active": False}
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False
    assert (
        await app_client.get("/api/summary", headers=auth_headers(session["access_token"]))
    ).status_code == 401

    refused = await app_client.post(
        "/api/auth/login", json={"username": "leaver", "password": "leaver-pass-123"}
    )
    assert refused.status_code == 403
    # A wrong password still gets the generic answer -- deactivation is only
    # revealed to someone who knows the password.
    wrong = await app_client.post("/api/auth/login", json={"username": "leaver", "password": "nope"})
    assert wrong.status_code == 401

    on = await app_client.post(
        f"/api/users/{target.id}/active", headers=auth_headers(admin_token), json={"active": True}
    )
    assert on.status_code == 200
    await _login(app_client, "leaver", "leaver-pass-123")


async def test_cannot_deactivate_self(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    admin_row = (await db_session.execute(select(User).where(User.username == "admin"))).scalar_one()
    response = await app_client.post(
        f"/api/users/{admin_row.id}/active", headers=auth_headers(admin_token), json={"active": False}
    )
    assert response.status_code == 400


async def test_there_is_no_delete_endpoint(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "keep.me")
    response = await app_client.delete(f"/api/users/{target.id}", headers=auth_headers(admin_token))
    assert response.status_code == 405


# --- Unlock, sessions, 2FA ----------------------------------------------------


async def test_unlock_clears_the_login_throttle(
    app_client: AsyncClient, test_app, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "guessed.at")
    throttle: LoginThrottle = test_app.state.login_throttle
    for _ in range(throttle.failure_threshold):
        throttle.record_failure("guessed.at")

    listed = await app_client.get("/api/users", headers=auth_headers(admin_token))
    assert next(u for u in listed.json() if u["username"] == "guessed.at")["throttled"] is True

    response = await app_client.post(f"/api/users/{target.id}/unlock", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["throttled"] is False


async def test_admin_can_list_and_end_one_session_of_a_user(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "two.devices", password="two-devices-123")
    first = await _login(app_client, "two.devices", "two-devices-123")
    second = await _login(app_client, "two.devices", "two-devices-123")

    sessions = await app_client.get(f"/api/users/{target.id}/sessions", headers=auth_headers(admin_token))
    assert sessions.status_code == 200
    assert len(sessions.json()) == 2

    first_claims_sid = (await _sid_of(db_session, target.id))[0]
    revoked = await app_client.delete(
        f"/api/users/{target.id}/sessions",
        headers=auth_headers(admin_token),
        params={"session_id": first_claims_sid},
    )
    assert revoked.json()["closed"] == 1

    statuses = {
        (await app_client.get("/api/summary", headers=auth_headers(s["access_token"]))).status_code
        for s in (first, second)
    }
    assert statuses == {200, 401}


async def _sid_of(db: AsyncSession, user_id: str) -> list[str]:
    rows = await db.execute(
        select(RefreshToken.session_id)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .order_by(RefreshToken.created_at)
    )
    return list(rows.scalars())


async def test_reset_2fa_turns_totp_off(
    app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession
):
    target = await _seed(db_session, "lost.phone")
    target.totp_secret = "JBSWY3DPEHPK3PXP"
    target.totp_enabled = True
    await db_session.commit()

    response = await app_client.post(f"/api/users/{target.id}/reset-2fa", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["totp_enabled"] is False


# --- Own password and sessions -------------------------------------------------


async def test_change_own_password_enforces_policy_and_history(
    app_client: AsyncClient, auth_headers, db_session: AsyncSession
):
    await _seed(db_session, "picky", password="Initial-Pass-2026!")
    token = (await _login(app_client, "picky", "Initial-Pass-2026!"))["access_token"]

    async def change(current: str, new: str) -> int:
        r = await app_client.post(
            "/api/auth/password",
            headers=auth_headers(token),
            json={"current_password": current, "new_password": new},
        )
        return r.status_code

    assert await change("wrong-current", NEW_PASSWORD) == 400
    assert await change("Initial-Pass-2026!", "short1A!") == 400
    assert await change("Initial-Pass-2026!", "picky-Is-My-Name-99") == 400  # contains username
    assert await change("Initial-Pass-2026!", "My-password-2026!!") == 400  # common word
    assert await change("Initial-Pass-2026!", NEW_PASSWORD) == 200
    # Back to the previous one -- in history.
    assert await change(NEW_PASSWORD, "Initial-Pass-2026!") == 400


async def test_change_own_password_closes_other_sessions(
    app_client: AsyncClient, auth_headers, db_session: AsyncSession
):
    await _seed(db_session, "roamer", password="Roamer-Pass-2026!")
    laptop = (await _login(app_client, "roamer", "Roamer-Pass-2026!"))["access_token"]
    phone = (await _login(app_client, "roamer", "Roamer-Pass-2026!"))["access_token"]

    response = await app_client.post(
        "/api/auth/password",
        headers=auth_headers(laptop),
        json={"current_password": "Roamer-Pass-2026!", "new_password": NEW_PASSWORD},
    )
    assert response.json()["sessions_closed"] == 1
    assert (await app_client.get("/api/summary", headers=auth_headers(laptop))).status_code == 200
    assert (await app_client.get("/api/summary", headers=auth_headers(phone))).status_code == 401


async def test_own_sessions_list_marks_current_and_can_close_others(
    app_client: AsyncClient, auth_headers, db_session: AsyncSession
):
    await _seed(db_session, "multi", password="multi-pass-123")
    current = (await _login(app_client, "multi", "multi-pass-123"))["access_token"]
    await _login(app_client, "multi", "multi-pass-123")

    listed = (await app_client.get("/api/auth/sessions", headers=auth_headers(current))).json()
    assert sorted(s["current"] for s in listed) == [False, True]
    current_id = next(s["id"] for s in listed if s["current"])

    refused = await app_client.delete(
        "/api/auth/sessions", headers=auth_headers(current), params={"session_id": current_id}
    )
    assert refused.status_code == 400
    closed = await app_client.delete("/api/auth/sessions", headers=auth_headers(current))
    assert closed.json()["closed"] == 1


async def test_logout_kills_the_access_token_immediately(app_client: AsyncClient, auth_headers):
    login = await _login(app_client, "admin", "admin-test-password-123")
    assert (await app_client.post("/api/auth/logout")).status_code == 204
    assert (
        await app_client.get("/api/summary", headers=auth_headers(login["access_token"]))
    ).status_code == 401


async def test_login_accepts_contact_email(app_client: AsyncClient):
    login = await _login(app_client, "Admin@Example.com", "admin-test-password-123")
    assert login["username"] == "admin"


# --- Branch admins: viewers in their own branch only ---------------------------


async def test_branch_admin_list_users_excludes_other_branches(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    await _seed(db_session, "other.branch", branch="branch-b")

    response = await app_client.get("/api/users", headers=auth_headers(branch_a_admin_token))
    assert response.status_code == 200
    usernames = {u["username"] for u in response.json()}
    assert "branch-a-admin" in usernames
    assert "other.branch" not in usernames


async def test_branch_admin_creates_viewer_in_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)
    body = await _create(app_client, branch_a_admin_token, username="new.viewer.a", role="viewer")
    assert body["user"]["branch"] == "branch-a"


async def test_branch_admin_cannot_create_unrestricted_viewer(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    """Explicitly requesting branch=null (unrestricted) from a branch-scoped
    admin must never actually produce an unrestricted account -- it's
    silently pinned to the actor's own branch instead, the same
    substitution behavior as api.deps.resolve_branch for query params."""
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)
    body = await _create(app_client, branch_a_admin_token, username="wannabe", role="viewer", branch=None)
    assert body["user"]["branch"] == "branch-a"


async def test_branch_admin_cannot_create_user_in_other_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, monkeypatch
):
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)
    response = await app_client.post(
        "/api/users",
        headers=auth_headers(branch_a_admin_token),
        json={"username": "sneaky", "role": "viewer", "branch": "branch-b"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["admin", "auditor", "superadmin"])
async def test_branch_admin_can_only_create_viewers(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, role: str
):
    response = await app_client.post(
        "/api/users", headers=auth_headers(branch_a_admin_token), json={"username": "climber", "role": role}
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_change_roles(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    viewer = await _seed(db_session, "a.viewer", branch="branch-a")
    response = await app_client.patch(
        f"/api/users/{viewer.id}/role", headers=auth_headers(branch_a_admin_token), json={"role": "admin"}
    )
    assert response.status_code == 403


async def test_branch_admin_manages_own_branch_viewer(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    viewer = await _seed(db_session, "a.viewer2", branch="branch-a")
    headers = auth_headers(branch_a_admin_token)
    assert (
        await app_client.post(f"/api/users/{viewer.id}/reset-password", headers=headers)
    ).status_code == 200
    deactivated = await app_client.post(
        f"/api/users/{viewer.id}/active", headers=headers, json={"active": False}
    )
    assert deactivated.status_code == 200


async def test_branch_admin_cannot_manage_another_admin_in_same_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    peer = await _seed(db_session, "peer.admin", role=UserRole.ADMIN, branch="branch-a")
    headers = auth_headers(branch_a_admin_token)
    assert (await app_client.post(f"/api/users/{peer.id}/reset-password", headers=headers)).status_code == 403
    assert (
        await app_client.post(f"/api/users/{peer.id}/active", headers=headers, json={"active": False})
    ).status_code == 403
    assert (
        await app_client.patch(f"/api/users/{peer.id}", headers=headers, json={"note": "x"})
    ).status_code == 403


@pytest.mark.parametrize(
    ("method", "path_suffix", "body"),
    [
        ("patch", "/role", {"role": "admin"}),
        ("post", "/reset-password", None),
        ("post", "/active", {"active": False}),
        ("patch", "/branch", {"branch": "branch-a"}),
        ("patch", "", {"full_name": "x"}),
        ("get", "/sessions", None),
    ],
)
async def test_branch_admin_cannot_reach_other_branch_user(
    app_client: AsyncClient,
    branch_a_admin_token,
    auth_headers,
    db_session: AsyncSession,
    method: str,
    path_suffix: str,
    body: dict | None,
):
    other = await _seed(db_session, "elsewhere", branch="branch-b")
    kwargs: dict = {"headers": auth_headers(branch_a_admin_token)}
    if body is not None:
        kwargs["json"] = body
    response = await getattr(app_client, method)(f"/api/users/{other.id}{path_suffix}", **kwargs)
    # 403 for role (super-admin-only before any lookup), 404 everywhere else
    # so a cross-branch id doesn't confirm the account exists.
    assert response.status_code == (403 if path_suffix == "/role" else 404)


async def test_branch_admin_cannot_change_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession, monkeypatch
):
    """The core privilege-escalation regression: api.deps.resolve_branch
    treats branch=None as unrestricted access to every branch's data, so a
    branch-scoped admin granting themselves branch=null would be a full
    escalation."""
    monkeypatch.setattr(user_service, "get_settings", _multi_branch_settings)
    admin_row = (await db_session.execute(select(User).where(User.username == "branch-a-admin"))).scalar_one()

    for branch in (None, "branch-b"):
        response = await app_client.patch(
            f"/api/users/{admin_row.id}/branch",
            headers=auth_headers(branch_a_admin_token),
            json={"branch": branch},
        )
        assert response.status_code in (400, 403)

    await db_session.refresh(admin_row)
    assert admin_row.branch == "branch-a"
