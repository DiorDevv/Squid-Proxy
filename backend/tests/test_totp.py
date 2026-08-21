"""Two-factor (TOTP) setup, login-challenge, recovery codes, and disable."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.totp import current_code
from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.totp_recovery_code import TotpRecoveryCode
from app.models.user import User


async def _enable_totp(app_client: AsyncClient, admin_token: str, auth_headers) -> tuple[str, list[str]]:
    """Runs the real setup -> confirm flow via the API and returns
    (secret, recovery_codes) -- shared by every test that needs 2FA already
    on rather than testing that flow itself."""
    setup = await app_client.post("/api/auth/totp/setup", headers=auth_headers(admin_token))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]

    confirm = await app_client.post(
        "/api/auth/totp/confirm",
        headers=auth_headers(admin_token),
        json={"code": current_code(secret)},
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


async def test_totp_setup_returns_secret_and_matching_otpauth_uri(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.post("/api/auth/totp/setup", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body["secret"]) >= 16
    assert body["secret"] in body["otpauth_uri"]
    assert body["otpauth_uri"].startswith("otpauth://totp/")


async def test_totp_setup_requires_auth(app_client: AsyncClient):
    response = await app_client.post("/api/auth/totp/setup")
    assert response.status_code == 401


async def test_totp_confirm_with_correct_code_enables_and_returns_ten_recovery_codes(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    secret, codes = await _enable_totp(app_client, admin_token, auth_headers)
    assert len(codes) == 10
    assert len(set(codes)) == 10  # all distinct

    user = (
        await db_session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    assert user.totp_enabled is True
    assert user.totp_secret == secret


async def test_totp_confirm_with_wrong_code_returns_400_and_stays_disabled(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await app_client.post("/api/auth/totp/setup", headers=auth_headers(admin_token))
    response = await app_client.post(
        "/api/auth/totp/confirm", headers=auth_headers(admin_token), json={"code": "000000"}
    )
    assert response.status_code == 400

    user = (
        await db_session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    assert user.totp_enabled is False


async def test_totp_confirm_records_audit_entry(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _enable_totp(app_client, admin_token, auth_headers)
    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.TOTP_ENABLED)
        )
    ).scalar_one()
    assert entry.target_email == "admin@example.com"


async def test_totp_status_reflects_enabled_state(app_client: AsyncClient, admin_token, auth_headers):
    before = await app_client.get("/api/auth/totp/status", headers=auth_headers(admin_token))
    assert before.json()["enabled"] is False

    await _enable_totp(app_client, admin_token, auth_headers)

    after = await app_client.get("/api/auth/totp/status", headers=auth_headers(admin_token))
    assert after.json()["enabled"] is True


async def test_login_with_totp_enabled_returns_mfa_challenge_not_tokens(
    app_client: AsyncClient, admin_token, auth_headers
):
    await _enable_totp(app_client, admin_token, auth_headers)

    response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is True
    assert body["challenge_token"]
    assert body["access_token"] is None
    assert "refresh_token" not in response.cookies


async def test_verify_mfa_with_correct_code_completes_login(
    app_client: AsyncClient, admin_token, auth_headers
):
    secret, _codes = await _enable_totp(app_client, admin_token, auth_headers)

    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    challenge_token = login.json()["challenge_token"]

    response = await app_client.post(
        "/api/auth/login/verify-mfa",
        json={"challenge_token": challenge_token, "code": current_code(secret)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["role"] == "admin"
    assert "refresh_token" in response.cookies


async def test_verify_mfa_with_wrong_code_returns_401(app_client: AsyncClient, admin_token, auth_headers):
    await _enable_totp(app_client, admin_token, auth_headers)
    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    challenge_token = login.json()["challenge_token"]

    response = await app_client.post(
        "/api/auth/login/verify-mfa", json={"challenge_token": challenge_token, "code": "000000"}
    )
    assert response.status_code == 401


async def test_verify_mfa_challenge_survives_one_wrong_attempt(
    app_client: AsyncClient, admin_token, auth_headers
):
    """A single wrong guess must not burn the challenge -- only
    MfaChallengeStore.MAX_ATTEMPTS consecutive failures should."""
    secret, _codes = await _enable_totp(app_client, admin_token, auth_headers)
    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    challenge_token = login.json()["challenge_token"]

    wrong = await app_client.post(
        "/api/auth/login/verify-mfa", json={"challenge_token": challenge_token, "code": "000000"}
    )
    assert wrong.status_code == 401

    right = await app_client.post(
        "/api/auth/login/verify-mfa",
        json={"challenge_token": challenge_token, "code": current_code(secret)},
    )
    assert right.status_code == 200


async def test_verify_mfa_challenge_invalidated_after_max_wrong_attempts(
    app_client: AsyncClient, admin_token, auth_headers
):
    secret, _codes = await _enable_totp(app_client, admin_token, auth_headers)
    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    challenge_token = login.json()["challenge_token"]

    for _ in range(5):
        await app_client.post(
            "/api/auth/login/verify-mfa", json={"challenge_token": challenge_token, "code": "000000"}
        )

    # Challenge is gone now -- even the *correct* code no longer works
    # against it, since the whole challenge_token was invalidated.
    response = await app_client.post(
        "/api/auth/login/verify-mfa",
        json={"challenge_token": challenge_token, "code": current_code(secret)},
    )
    assert response.status_code == 401


async def test_verify_mfa_with_recovery_code_works_and_consumes_it(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    _secret, codes = await _enable_totp(app_client, admin_token, auth_headers)
    recovery_code = codes[0]

    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    challenge_token = login.json()["challenge_token"]

    response = await app_client.post(
        "/api/auth/login/verify-mfa", json={"challenge_token": challenge_token, "code": recovery_code}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]

    used = (
        await db_session.execute(
            select(TotpRecoveryCode).where(TotpRecoveryCode.used_at.is_not(None))
        )
    ).scalars().all()
    assert len(used) == 1


async def test_recovery_code_cannot_be_reused(app_client: AsyncClient, admin_token, auth_headers):
    _secret, codes = await _enable_totp(app_client, admin_token, auth_headers)
    recovery_code = codes[0]

    async def _login_challenge() -> str:
        login = await app_client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-test-password-123"},
        )
        return login.json()["challenge_token"]

    first = await app_client.post(
        "/api/auth/login/verify-mfa",
        json={"challenge_token": await _login_challenge(), "code": recovery_code},
    )
    assert first.status_code == 200

    second = await app_client.post(
        "/api/auth/login/verify-mfa",
        json={"challenge_token": await _login_challenge(), "code": recovery_code},
    )
    assert second.status_code == 401


async def test_totp_disable_requires_correct_password(app_client: AsyncClient, admin_token, auth_headers):
    await _enable_totp(app_client, admin_token, auth_headers)
    response = await app_client.post(
        "/api/auth/totp/disable", headers=auth_headers(admin_token), json={"password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_totp_disable_with_correct_password_disables_2fa(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _enable_totp(app_client, admin_token, auth_headers)
    response = await app_client.post(
        "/api/auth/totp/disable",
        headers=auth_headers(admin_token),
        json={"password": "admin-test-password-123"},
    )
    assert response.status_code == 204

    user = (
        await db_session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    assert user.totp_enabled is False
    assert user.totp_secret is None

    # A normal login (no challenge) works again.
    login = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert login.json()["mfa_required"] is False
    assert login.json()["access_token"]


async def test_totp_disable_deletes_recovery_codes(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _enable_totp(app_client, admin_token, auth_headers)
    await app_client.post(
        "/api/auth/totp/disable",
        headers=auth_headers(admin_token),
        json={"password": "admin-test-password-123"},
    )
    remaining = (await db_session.execute(select(TotpRecoveryCode))).scalars().all()
    assert remaining == []
