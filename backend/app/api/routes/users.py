from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_admin, require_reauth
from app.core import permissions as permission_catalog
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import LoginThrottle
from app.models.user import User
from app.schemas.auth import SessionOut, SessionsRevokedResponse
from app.schemas.users import (
    UserActiveRequest,
    UserBranchUpdateRequest,
    UserCreatedResponse,
    UserCreateRequest,
    UserExpiryUpdateRequest,
    UserPasswordResetResponse,
    UserPermissionsUpdateRequest,
    UserProfileUpdateRequest,
    UserRoleUpdateRequest,
    UserSummary,
)
from app.services import session_service, user_service

# Super admins manage everyone, admins manage viewers in their own scope --
# that split is enforced per action in user_service. Every action that
# changes who can get in (create, role, branch, password, active state,
# sessions, 2FA) additionally needs a recent password confirmation
# (require_reauth); descriptive edits and unlocking don't.
router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _throttle(request: Request) -> LoginThrottle:
    return request.app.state.login_throttle


async def _summaries(request: Request, db: AsyncSession, users: list[User]) -> list[UserSummary]:
    counts = await user_service.session_counts(db, [u.id for u in users])
    throttle = _throttle(request)
    return [
        UserSummary.model_validate(u, from_attributes=True).model_copy(
            update={
                "active_sessions": counts.get(u.id, 0),
                "throttled": throttle.is_throttled(LoginThrottle.key(u.username)),
                "branches": list(u.branch_scope) if u.branch_scope is not None else None,
                "effective_permissions": sorted(permission_catalog.effective(u.role.value, u.permissions)),
            }
        )
        for u in users
    ]


async def _summary(request: Request, db: AsyncSession, user: User) -> UserSummary:
    return (await _summaries(request, db, [user]))[0]


@router.get("", response_model=list[UserSummary])
async def read_users(
    request: Request, db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(require_admin)
) -> list[UserSummary]:
    return await _summaries(request, db, await user_service.list_users(db, current_user))


@router.post("", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def create_user(
    request: Request,
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserCreatedResponse:
    user, temporary_password = await user_service.create_user(
        db,
        current_user,
        username=body.username,
        role=body.role,
        full_name=body.full_name,
        note=body.note,
        email=str(body.email) if body.email else None,
        branch=body.branch,
        branches=body.branches,
        permissions=body.permissions,
        expires_at=body.expires_at,
    )
    return UserCreatedResponse(user=await _summary(request, db, user), temporary_password=temporary_password)


@router.patch("/{user_id}", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_profile(
    request: Request,
    user_id: str,
    body: UserProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> UserSummary:
    sent = body.model_fields_set
    kwargs: dict = {"full_name": body.full_name}
    if "note" in sent:
        kwargs["note"] = body.note
    if "email" in sent:
        kwargs["email"] = str(body.email) if body.email else None
    user = await user_service.update_profile(db, user_id, current_user, **kwargs)
    return await _summary(request, db, user)


@router.patch("/{user_id}/role", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_role(
    request: Request,
    user_id: str,
    body: UserRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    user = await user_service.update_role(db, user_id, body.role, current_user)
    return await _summary(request, db, user)


@router.patch("/{user_id}/branch", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_branch(
    request: Request,
    user_id: str,
    body: UserBranchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    if "branches" in body.model_fields_set:
        user = await user_service.update_branches(db, user_id, body.branches, current_user)
    else:
        user = await user_service.update_branch(db, user_id, body.branch, current_user)
    return await _summary(request, db, user)


@router.patch("/{user_id}/permissions", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_permissions(
    request: Request,
    user_id: str,
    body: UserPermissionsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    user = await user_service.update_permissions(db, user_id, body.permissions, current_user)
    return await _summary(request, db, user)


@router.patch("/{user_id}/expiry", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_expiry(
    request: Request,
    user_id: str,
    body: UserExpiryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    user = await user_service.update_expiry(db, user_id, body.expires_at, current_user)
    return await _summary(request, db, user)


@router.post("/{user_id}/reset-password", response_model=UserPasswordResetResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def reset_user_password(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserPasswordResetResponse:
    user, temporary_password = await user_service.reset_password(db, user_id, current_user)
    return UserPasswordResetResponse(
        user=await _summary(request, db, user), temporary_password=temporary_password
    )


@router.post("/{user_id}/active", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def set_user_active(
    request: Request,
    user_id: str,
    body: UserActiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    user = await user_service.set_active(db, user_id, body.active, current_user)
    if body.active:
        _throttle(request).clear(LoginThrottle.key(user.username))
    return await _summary(request, db, user)


@router.post("/{user_id}/unlock", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def unlock_user(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> UserSummary:
    user = await user_service.get_manageable_user(db, user_id, current_user)
    throttle = _throttle(request)
    throttle.clear(LoginThrottle.key(user.username))
    if user.email:
        throttle.clear(LoginThrottle.key(user.email))
    await user_service.record_unlock(db, user, current_user)
    return await _summary(request, db, user)


@router.post("/{user_id}/reset-2fa", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def reset_user_totp(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> UserSummary:
    user = await user_service.reset_totp(db, user_id, current_user)
    return await _summary(request, db, user)


@router.get("/{user_id}/sessions", response_model=list[SessionOut])
async def read_user_sessions(
    user_id: str, db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(require_admin)
) -> list[SessionOut]:
    user = await user_service.get_manageable_user(db, user_id, current_user)
    rows = await session_service.list_sessions(db, user.id)
    return [session_service.to_out(row, current_user.session_id) for row in rows]


@router.delete("/{user_id}/sessions", response_model=SessionsRevokedResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def revoke_user_sessions(
    request: Request,
    user_id: str,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_reauth),
) -> SessionsRevokedResponse:
    """All of the user's sessions, or just `session_id`. The actor's own
    current session is always spared."""
    closed = await user_service.revoke_sessions(db, user_id, current_user, session_id=session_id)
    return SessionsRevokedResponse(closed=closed)
