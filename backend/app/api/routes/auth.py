import logging
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_current_user_pending_ok, get_db
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import (
    LoginThrottle,
    MfaChallengeStore,
    create_access_token,
    decode_refresh_cookie_value,
    encode_refresh_cookie_value,
    verify_password,
    verify_refresh_secret,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    ReauthRequest,
    ReauthResponse,
    RefreshResponse,
    SessionOut,
    SessionsRevokedResponse,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpStatusResponse,
    VerifyMfaRequest,
    WsTicketResponse,
)
from app.services import session_service, totp_service, user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
)
ACCOUNT_DISABLED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated."
)
INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
)


def _cookie_kwargs() -> dict:
    settings = get_settings()
    secure = (
        settings.ENVIRONMENT == "production" if settings.COOKIE_SECURE is None else settings.COOKIE_SECURE
    )
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
        "path": REFRESH_COOKIE_PATH,
    }


def _set_refresh_cookie(response: Response, row: RefreshToken, raw_secret: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=encode_refresh_cookie_value(row.jti, raw_secret),
        max_age=int((row.expires_at - datetime.now(UTC)).total_seconds()),
        **_cookie_kwargs(),
    )


async def _find_login_user(db: AsyncSession, login: str) -> User | None:
    login = login.strip().lower()
    column = User.email if "@" in login else User.username
    return (await db.execute(select(User).where(func.lower(column) == login))).scalar_one_or_none()


async def _complete_login(
    request: Request, response: Response, db: AsyncSession, user: User
) -> LoginResponse:
    """Password (and code, if 2FA is on) verified -- start a session. The
    sign-in itself counts as a fresh re-authentication (reauth_at)."""
    settings = get_settings()
    now = datetime.now(UTC)
    user.last_login_at = now
    user.last_login_ip = session_service.client_ip(request)
    row, raw_secret = session_service.new_token(db, request, user.id, reauth_at=now)
    await db.commit()
    _set_refresh_cookie(response, row, raw_secret)
    access_token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        branch=user.branch,
        token_version=user.token_version,
        session_id=row.session_id,
    )
    return LoginResponse(
        access_token=access_token,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role.value,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        branch=user.branch,
        must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().LOGIN_RATE_LIMIT)
async def login(
    request: Request, response: Response, credentials: LoginRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    throttle: LoginThrottle = request.app.state.login_throttle
    throttle_key = LoginThrottle.key(credentials.username)

    if not throttle.allow_attempt(throttle_key):
        # This account has too many recent failed logins and not enough time
        # has passed since the last one (see LoginThrottle). Burn the same
        # bcrypt time and return the same error as an ordinary wrong
        # password so a caller can't tell it tripped the throttle.
        verify_password(credentials.password, None)
        raise INVALID_CREDENTIALS

    user = await _find_login_user(db, credentials.username)
    password_ok = verify_password(credentials.password, user.hashed_password if user else None)
    if user is None or not password_ok:
        throttle.record_failure(throttle_key)
        raise INVALID_CREDENTIALS

    # Password was correct -- clear this account's failure record even if MFA
    # is still pending below (the credential-guessing threat is over; the
    # code step has its own attempt cap in MfaChallengeStore).
    throttle.record_success(throttle_key)

    # Only revealed to someone who already knows the password -- telling
    # them why is more useful than a generic failure.
    if not user.is_active:
        raise ACCOUNT_DISABLED

    if user.totp_enabled:
        # Password alone isn't enough -- hand back a short-lived, single-use
        # challenge instead of real tokens; the frontend prompts for a code
        # and completes login via POST /login/verify-mfa. No refresh cookie
        # is set yet, so an intercepted challenge_token alone (without the
        # code too) grants nothing.
        store: MfaChallengeStore = request.app.state.mfa_challenge_store
        challenge_token = store.issue(user.id)
        return LoginResponse(mfa_required=True, challenge_token=challenge_token)

    return await _complete_login(request, response, db, user)


@router.post("/login/verify-mfa", response_model=LoginResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def verify_mfa(
    request: Request, response: Response, body: VerifyMfaRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    store: MfaChallengeStore = request.app.state.mfa_challenge_store
    user_id = store.peek(body.challenge_token)
    if user_id is None:
        raise INVALID_CREDENTIALS

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.totp_enabled or not user.is_active:
        raise INVALID_CREDENTIALS

    if not await totp_service.verify_login_code(db, user, body.code):
        store.record_failure(body.challenge_token)
        raise INVALID_CREDENTIALS

    store.consume(body.challenge_token)
    return await _complete_login(request, response, db, user)


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> RefreshResponse:
    settings = get_settings()
    raw_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_cookie:
        raise INVALID_REFRESH

    decoded = decode_refresh_cookie_value(raw_cookie)
    if decoded is None:
        raise INVALID_REFRESH
    jti, raw_secret = decoded

    token_row = (await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))).scalar_one_or_none()

    if (
        token_row is None
        or token_row.revoked
        or token_row.expires_at < datetime.now(UTC)
        or not verify_refresh_secret(raw_secret, token_row.token_hash)
    ):
        # Reuse of a revoked/expired/invalid token is treated as a possible
        # theft signal -- revoke every other still-active session for this
        # user defensively, not just the one replayed token (a stolen token
        # rotated forward by an attacker would otherwise leave the
        # attacker-issued descendant token valid).
        if token_row is not None:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == token_row.user_id, RefreshToken.revoked.is_(False))
                .values(revoked=True)
            )
            await db.commit()
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise INVALID_REFRESH

    # Rotate atomically: flip revoked False -> True in a single UPDATE gated
    # on it still being False, so two concurrent requests replaying the same
    # cookie can't both pass the `token_row.revoked` check above and both
    # mint a new token from it. Only the request whose UPDATE actually
    # matched a row proceeds; the other is treated as a reuse.
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    # A Core UPDATE always executes through the DBAPI cursor, so this is
    # really a CursorResult at runtime -- AsyncSession.execute()'s stub
    # return type is the more general Result, which doesn't declare
    # .rowcount (only CursorResult does).
    if cast(CursorResult, result).rowcount == 0:
        await db.rollback()
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise INVALID_REFRESH

    user = (await db.execute(select(User).where(User.id == token_row.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        await db.commit()
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise INVALID_REFRESH

    # Same session, next token: everything that describes the session (not
    # this one token) carries forward.
    row, new_secret = session_service.new_token(
        db,
        request,
        user.id,
        session_id=token_row.session_id,
        session_started_at=token_row.session_started_at,
        reauth_at=token_row.reauth_at,
    )
    await db.commit()
    _set_refresh_cookie(response, row, new_secret)

    access_token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        branch=user.branch,
        token_version=user.token_version,
        session_id=row.session_id,
    )
    return RefreshResponse(
        access_token=access_token, expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    raw_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_cookie:
        decoded = decode_refresh_cookie_value(raw_cookie)
        if decoded:
            jti, _ = decoded
            token_row = (
                await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
            ).scalar_one_or_none()
            if token_row is not None:
                token_row.revoked = True
                await db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post("/ws-ticket", response_model=WsTicketResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def issue_ws_ticket(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> WsTicketResponse:
    store = request.app.state.ws_ticket_store
    # token_version travels with the ticket so the socket's periodic
    # re-check (see routes/ws.py) closes it the moment the account is
    # invalidated, not just on branch change.
    user = await _load_current_user(db, current_user)
    ticket = store.issue(
        user_id=current_user.user_id,
        role=current_user.role,
        branch=current_user.branch,
        token_version=user.token_version,
    )
    return WsTicketResponse(ticket=ticket, expires_in_seconds=int(store.ttl_seconds))


async def _load_current_user(db: AsyncSession, current_user: CurrentUser) -> User:
    user = (await db.execute(select(User).where(User.id == current_user.user_id))).scalar_one_or_none()
    if user is None:
        raise INVALID_CREDENTIALS
    return user


@router.get("/totp/status", response_model=TotpStatusResponse)
async def get_totp_status(
    db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)
) -> TotpStatusResponse:
    user = await _load_current_user(db, current_user)
    return TotpStatusResponse(enabled=user.totp_enabled)


@router.post("/totp/setup", response_model=TotpSetupResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def setup_totp(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TotpSetupResponse:
    user = await _load_current_user(db, current_user)
    secret, otpauth_uri = totp_service.begin_setup(user)
    await db.commit()
    return TotpSetupResponse(secret=secret, otpauth_uri=otpauth_uri)


@router.post("/totp/confirm", response_model=TotpConfirmResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def confirm_totp(
    request: Request,
    body: TotpConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TotpConfirmResponse:
    user = await _load_current_user(db, current_user)
    codes = await totp_service.confirm_setup(db, user, body.code, current_user.user_id)
    return TotpConfirmResponse(recovery_codes=codes)


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def disable_totp(
    request: Request,
    body: TotpDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    user = await _load_current_user(db, current_user)
    await totp_service.disable(db, user, body.password, current_user.user_id)


# --- Own profile, re-authentication, password and sessions -----------------


@router.get("/me", response_model=MeResponse)
async def read_me(
    db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(get_current_user_pending_ok)
) -> MeResponse:
    user = await _load_current_user(db, current_user)
    return MeResponse.model_validate(user, from_attributes=True).model_copy(update={"role": user.role.value})


async def _check_own_password(request: Request, db: AsyncSession, user: User, password: str) -> None:
    """Re-checks the signed-in user's password with the same per-account
    throttle as login -- someone holding a stolen session must not get an
    unthrottled password oracle."""
    throttle: LoginThrottle = request.app.state.login_throttle
    key = LoginThrottle.key(user.username)
    if not throttle.allow_attempt(key):
        verify_password(password, None)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again in a minute.",
        )
    if not verify_password(password, user.hashed_password):
        throttle.record_failure(key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    throttle.record_success(key)


@router.post("/reauth", response_model=ReauthResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def reauth(
    request: Request,
    body: ReauthRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReauthResponse:
    """Confirms the password again so this session may perform sensitive
    user-management actions for the next REAUTH_MINUTES (deps.require_reauth)."""
    if current_user.session_id is None:
        # A pre-session token -- nothing to attach the confirmation to.
        raise INVALID_REFRESH
    user = await _load_current_user(db, current_user)
    await _check_own_password(request, db, user, body.password)
    await session_service.mark_reauth(db, current_user.session_id)
    await db.commit()
    return ReauthResponse(valid_minutes=get_settings().REAUTH_MINUTES)


@router.post("/password", response_model=ChangePasswordResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_pending_ok),
) -> ChangePasswordResponse:
    user = await _load_current_user(db, current_user)
    await _check_own_password(request, db, user, body.current_password)
    closed = await user_service.change_own_password(
        db, user, body.current_password, body.new_password, keep_session_id=current_user.session_id
    )
    return ChangePasswordResponse(sessions_closed=closed)


@router.get("/sessions", response_model=list[SessionOut])
async def read_my_sessions(
    db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)
) -> list[SessionOut]:
    rows = await session_service.list_sessions(db, current_user.user_id)
    return [session_service.to_out(row, current_user.session_id) for row in rows]


@router.delete("/sessions", response_model=SessionsRevokedResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def revoke_my_sessions(
    request: Request,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SessionsRevokedResponse:
    """Signs out my other sessions (all, or the one `session_id`). The
    current session is never closed here -- that's what /logout is for."""
    if session_id is not None and session_id == current_user.session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Use sign out to end the current session."
        )
    closed = await session_service.revoke(
        db, current_user.user_id, session_id=session_id, keep_session_id=current_user.session_id
    )
    await db.commit()
    return SessionsRevokedResponse(closed=closed)
