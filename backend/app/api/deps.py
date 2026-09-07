from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.db import get_session
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, role: str, branch: str | None = None) -> None:
        self.user_id = user_id
        self.role = role
        # None means unrestricted (every user today) -- set to one branch
        # tag to scope this account to only that branch's data, see
        # resolve_branch below.
        self.branch = branch


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession]:
    yield session


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
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
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise unauthorized

    # A token minted before token_version existed carries tv=None -- accept
    # it (the user-still-exists check above already ran; these age out
    # within one access-token lifetime), but a present, non-matching tv
    # means the account was deliberately invalidated (password reset,
    # role/branch change) since this token was issued.
    token_tv = payload.get("tv")
    if token_tv is not None and token_tv != user.token_version:
        raise unauthorized

    return CurrentUser(user_id=user.id, role=user.role.value, branch=user.branch)


def require_role(*allowed_roles: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return checker


# admin: full read + every mutation. viewer: full read, no mutations.
# auditor: everything a viewer reads, PLUS the audit log and the
# retention/policy surface, and still no mutations (see docs/PRODUCT.md).
require_admin = require_role("admin")
require_any_role = require_role("admin", "viewer", "auditor")
require_admin_or_auditor = require_role("admin", "auditor")


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
