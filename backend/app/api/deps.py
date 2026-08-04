from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.db import get_session

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


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise unauthorized from exc

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or not role:
        raise unauthorized
    # .get (not required) -- a token issued before branch-scoping existed
    # has no "branch" claim at all; treat that the same as an explicit
    # None (unrestricted) rather than erroring an already-logged-in session.
    branch = payload.get("branch")
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def require_role(*allowed_roles: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return checker


require_admin = require_role("admin")
require_any_role = require_role("admin", "viewer")


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
