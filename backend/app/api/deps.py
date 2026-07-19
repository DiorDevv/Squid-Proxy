from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.db import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, role: str) -> None:
        self.user_id = user_id
        self.role = role


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
    return CurrentUser(user_id=user_id, role=role)


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
