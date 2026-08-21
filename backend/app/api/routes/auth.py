import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import (
    MfaChallengeStore,
    create_access_token,
    decode_refresh_cookie_value,
    encode_refresh_cookie_value,
    generate_refresh_secret,
    verify_password,
    verify_refresh_secret,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpStatusResponse,
    VerifyMfaRequest,
    WsTicketResponse,
)
from app.services import totp_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
)
INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
)


def _cookie_kwargs() -> dict:
    settings = get_settings()
    return {
        "httponly": True,
        "secure": settings.ENVIRONMENT == "production",
        "samesite": "strict",
        "path": REFRESH_COOKIE_PATH,
    }


async def _issue_refresh_cookie(response: Response, db: AsyncSession, user_id: str) -> None:
    jti, raw_secret, secret_hash, expires_at = generate_refresh_secret()
    db.add(RefreshToken(jti=jti, user_id=user_id, token_hash=secret_hash, expires_at=expires_at))
    await db.commit()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=encode_refresh_cookie_value(jti, raw_secret),
        max_age=int((expires_at - datetime.now(UTC)).total_seconds()),
        **_cookie_kwargs(),
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().LOGIN_RATE_LIMIT)
async def login(
    request: Request, response: Response, credentials: LoginRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    settings = get_settings()
    user = (await db.execute(select(User).where(User.email == credentials.email))).scalar_one_or_none()
    password_ok = verify_password(credentials.password, user.hashed_password if user else None)
    if user is None or not password_ok:
        raise INVALID_CREDENTIALS

    if user.totp_enabled:
        # Password alone isn't enough -- hand back a short-lived, single-use
        # challenge instead of real tokens; the frontend prompts for a code
        # and completes login via POST /login/verify-mfa. No refresh cookie
        # is set yet, so an intercepted challenge_token alone (without the
        # code too) grants nothing.
        store: MfaChallengeStore = request.app.state.mfa_challenge_store
        challenge_token = store.issue(user.id)
        return LoginResponse(mfa_required=True, challenge_token=challenge_token)

    access_token = create_access_token(user_id=user.id, role=user.role.value, branch=user.branch)
    await _issue_refresh_cookie(response, db, user.id)

    return LoginResponse(
        access_token=access_token,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role.value,
        email=user.email,
        branch=user.branch,
    )


@router.post("/login/verify-mfa", response_model=LoginResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def verify_mfa(
    request: Request, response: Response, body: VerifyMfaRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    settings = get_settings()
    store: MfaChallengeStore = request.app.state.mfa_challenge_store
    user_id = store.peek(body.challenge_token)
    if user_id is None:
        raise INVALID_CREDENTIALS

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.totp_enabled:
        raise INVALID_CREDENTIALS

    if not await totp_service.verify_login_code(db, user, body.code):
        store.record_failure(body.challenge_token)
        raise INVALID_CREDENTIALS

    store.consume(body.challenge_token)
    access_token = create_access_token(user_id=user.id, role=user.role.value, branch=user.branch)
    await _issue_refresh_cookie(response, db, user.id)

    return LoginResponse(
        access_token=access_token,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role.value,
        email=user.email,
        branch=user.branch,
    )


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

    token_row = (
        await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one_or_none()

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
    if result.rowcount == 0:
        await db.rollback()
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise INVALID_REFRESH

    user = (await db.execute(select(User).where(User.id == token_row.user_id))).scalar_one_or_none()
    if user is None:
        raise INVALID_REFRESH

    await _issue_refresh_cookie(response, db, user.id)

    access_token = create_access_token(user_id=user.id, role=user.role.value, branch=user.branch)
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
    request: Request, current_user: CurrentUser = Depends(get_current_user)
) -> WsTicketResponse:
    store = request.app.state.ws_ticket_store
    ticket = store.issue(user_id=current_user.user_id, role=current_user.role, branch=current_user.branch)
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
