from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy import exists, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models.db import get_session
from app.models.refresh_token import RefreshToken
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# Machine-readable 403 details the frontend keys on (see
# frontend/src/lib/api-client.ts) -- kept as exact strings, not prose.
PASSWORD_CHANGE_REQUIRED = "password_change_required"
REAUTH_REQUIRED = "reauth_required"


class CurrentUser:
    def __init__(
        self,
        user_id: str,
        role: str,
        branch: str | None = None,
        session_id: str | None = None,
        username: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.role = role
        # None means unrestricted (every user today) -- set to one branch
        # tag to scope this account to only that branch's data, see
        # resolve_branch below.
        self.branch = branch
        # The sign-in session this request's access token belongs to (None
        # for a token minted before sessions carried an id).
        self.session_id = session_id
        self.username = username

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession]:
    yield session


async def _authenticate(token: str | None, session: AsyncSession) -> tuple[User, str | None]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise unauthorized from exc

    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized

    # One SELECT per authenticated request -- the app is a dashboard, not a
    # high-QPS API, and the alternative (trusting the JWT's role/branch for
    # the full token lifetime) means a demotion, branch reassignment, or
    # account deletion silently doesn't take effect for up to
    # ACCESS_TOKEN_EXPIRE_MINUTES. role/branch are read from the live row,
    # not the token, so a change lands on the very next request.
    #
    # The same SELECT also checks that the token's sign-in session (its
    # `sid` claim) is still live: a session revoked on its own (sign-out,
    # "end this session") must stop working now, not when its access token
    # expires. A token without a sid predates sessions and skips this.
    session_id = payload.get("sid")
    session_live = (
        exists().where(
            RefreshToken.session_id == session_id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        if session_id is not None
        else true()
    )
    row = (await session.execute(select(User, session_live).where(User.id == user_id))).one_or_none()
    if row is None:
        raise unauthorized
    user, live = row

    # A token minted before token_version existed carries tv=None -- accept
    # it (the user-still-exists check above already ran; these age out
    # within one access-token lifetime), but a present, non-matching tv
    # means the account was deliberately invalidated (password reset,
    # role/branch change) since this token was issued.
    token_tv = payload.get("tv")
    if token_tv is not None and token_tv != user.token_version:
        raise unauthorized

    # Deactivation also bumps token_version, so this is belt-and-braces for
    # a token minted without a tv claim.
    if not user.is_active or not live:
        raise unauthorized

    return user, session_id


def _current_user(user: User, session_id: str | None) -> CurrentUser:
    return CurrentUser(
        user_id=user.id,
        role=user.role.value,
        branch=user.branch,
        session_id=session_id,
        username=user.username,
    )


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    user, session_id = await _authenticate(token, session)
    # An account still on its admin-issued temporary password may do
    # nothing but change it (routes using get_current_user_pending_ok).
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    return _current_user(user, session_id)


async def get_current_user_pending_ok(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """get_current_user minus the must_change_password gate -- only for
    reading one's own profile and changing one's own password."""
    user, session_id = await _authenticate(token, session)
    return _current_user(user, session_id)


def require_role(*allowed_roles: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return checker


# superadmin: everything an admin can do, plus managing admins/auditors/
# other super admins (see app/services/user_service.py); always
# unrestricted. admin: full read + every mutation, and managing *viewers*
# in their own scope. viewer: full read, no mutations. auditor: everything
# a viewer reads, PLUS the audit log and the retention/policy surface, and
# still no mutations (see docs/PRODUCT.md).
require_superadmin = require_role("superadmin")
require_admin = require_role("superadmin", "admin")
require_any_role = require_role("superadmin", "admin", "viewer", "auditor")
require_admin_or_auditor = require_role("superadmin", "admin", "auditor")


async def require_reauth(
    current_user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """For sensitive user-management actions: the actor must have entered
    their password (sign-in, or POST /api/auth/reauth) within
    REAUTH_MINUTES on *this* session -- a stolen, still-valid session
    alone isn't enough to mint accounts or reset passwords. 403 with
    REAUTH_REQUIRED tells the frontend to prompt and retry."""
    reauth_required = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=REAUTH_REQUIRED)
    if current_user.session_id is None:
        raise reauth_required
    cutoff = datetime.now(UTC) - timedelta(minutes=get_settings().REAUTH_MINUTES)
    fresh = (
        await session.execute(
            select(RefreshToken.id)
            .where(
                RefreshToken.session_id == current_user.session_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.reauth_at >= cutoff,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if fresh is None:
        raise reauth_required
    return current_user


async def resolve_branch(
    branch: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> str | None:
    """Drop-in replacement for `branch: str | None = Query(default=None)` on
    every data-read route -- one shared enforcement point instead of ~20
    separate checks. An unrestricted user (current_user.branch is None,
    every user before this feature and every admin/viewer not explicitly
    scoped) passes the requested branch through unchanged, including None
    ("all branches"), so nothing changes for them. A branch-scoped user
    always gets their own branch's data: silently substituted if they
    didn't ask for a specific branch, rejected with 403 if they explicitly
    asked for a *different* one (rather than silently overriding it, which
    would hide the fact that the request as-sent wasn't honored)."""
    if current_user.branch is None:
        return branch
    if branch is not None and branch != current_user.branch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this branch."
        )
    return current_user.branch
