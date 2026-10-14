from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy import exists, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as permission_catalog
from app.core.branch_scope import BranchScope, as_scope, normalize_branches, scope_tag
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
        branches: Iterable[str] | None = None,
        permissions: Iterable[str] | None = None,
    ) -> None:
        self.user_id = user_id
        self.role = role
        # None means unrestricted -- otherwise the sorted branch tags this
        # account is limited to (see core/branch_scope.py and
        # resolve_branch below). `branch` is the single-branch shorthand.
        self.branches: tuple[str, ...] | None = normalize_branches(
            branches if branches is not None else ([branch] if branch else None)
        )
        # The sign-in session this request's access token belongs to (None
        # for a token minted before sessions carried an id).
        self.session_id = session_id
        self.username = username
        # Explicit permission list, or None for the role's defaults.
        self.permissions: frozenset[str] = permission_catalog.effective(
            role, list(permissions) if permissions is not None else None
        )

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"

    @property
    def is_restricted(self) -> bool:
        return self.branches is not None

    @property
    def scope(self) -> BranchScope:
        """This account's full reach as a BranchScope (None, one tag, or
        a tuple) -- what a data route uses when nothing narrower is asked."""
        return as_scope(self.branches)

    @property
    def branch(self) -> str | None:
        """Scope tag: None only when unrestricted. Kept for call sites that
        compare a single stored branch against it -- for a multi-branch
        account the joined tag never equals one branch, so those fail
        closed. New code should use can_access()/scope instead."""
        return scope_tag(self.scope)

    def can_access(self, branch: str | None) -> bool:
        """May this account see rows tagged with `branch`? A None/empty tag
        (a row with no branch dimension, or one covering every branch) is
        only visible to an unrestricted account."""
        if self.branches is None:
            return True
        return branch is not None and branch in self.branches

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


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
    # a token minted without a tv claim. An account past its expires_at is
    # cut off on the very next request, same as a deactivated one.
    if not user.is_active or not live or user.is_expired():
        raise unauthorized

    return user, session_id


def _current_user(user: User, session_id: str | None) -> CurrentUser:
    return CurrentUser(
        user_id=user.id,
        role=user.role.value,
        branches=user.branch_scope,
        session_id=session_id,
        username=user.username,
        permissions=user.permissions,
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


def require_permission(permission: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Gates one feature area (core/permissions.py) instead of a role --
    a viewer granted "export" may export; an admin without "alerts" may
    not change alert settings."""

    async def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return checker


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


NO_BRANCH_ACCESS_DETAIL = "You do not have access to this branch."


async def resolve_branch(
    branch: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> BranchScope:
    """Drop-in replacement for `branch: str | None = Query(default=None)` on
    every data-read route -- one shared enforcement point instead of ~20
    separate checks. Returns a BranchScope (core/branch_scope.py):

    - Unrestricted user: the requested branch passes through unchanged,
      including None ("all branches").
    - Branch-limited user: a requested branch inside their set is honored;
      one outside it is a 403 (rather than silently overridden, which would
      hide that the request as-sent wasn't honored). Nothing requested means
      their whole set -- one tag, or a tuple for a multi-branch account,
      which services filter with branch_filter() as `IN (...)`."""
    if not current_user.is_restricted:
        return branch
    if branch is not None:
        if not current_user.can_access(branch):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NO_BRANCH_ACCESS_DETAIL)
        return branch
    return current_user.scope
