"""Admin-only user management: list/create/role-change/password-reset/delete.

There is no self-service signup or password-reset-by-email flow -- this is
an internal security tool provisioned by an admin, matching how
`scripts/create_admin.py` already worked before this module existed. These
functions are the same operations, exposed over the API instead of the CLI,
plus role/password/delete management the CLI script never had.
"""

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.audit_log import AuditAction
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services import audit_service

EMAIL_TAKEN = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists."
)
USER_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
CANNOT_MODIFY_SELF = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="You cannot change your own role or delete your own account here -- sign in as another admin.",
)
LAST_ADMIN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Cannot remove the last remaining admin account.",
)


def _validate_branch(branch: str | None) -> None:
    """None (unrestricted) always passes -- only a *non-null* branch is
    checked against the configured set, so a typo here can't silently lock
    a user out of everything instead of failing loudly at creation/update
    time."""
    if branch is None:
        return
    valid_branches = {source.branch for source in get_settings().effective_log_sources}
    if branch not in valid_branches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown branch {branch!r}. Configured branches: {', '.join(sorted(valid_branches))}.",
        )


async def list_users(session: AsyncSession) -> list[User]:
    rows = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
    return list(rows)


async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    role: UserRole,
    actor_user_id: str,
    branch: str | None = None,
) -> User:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise EMAIL_TAKEN
    _validate_branch(branch)

    user = User(email=email, hashed_password=hash_password(password), role=role, branch=branch)
    session.add(user)
    await audit_service.record(
        session,
        action=AuditAction.USER_CREATED,
        actor_user_id=actor_user_id,
        target_email=email,
        detail=f"role={role.value}, branch={branch or 'unrestricted'}",
    )
    await session.commit()
    await session.refresh(user)
    return user


async def _get_user_or_404(session: AsyncSession, user_id: str) -> User:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise USER_NOT_FOUND
    return user


async def _count_admins(session: AsyncSession) -> int:
    return (
        await session.execute(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN))
    ).scalar_one()


async def update_role(session: AsyncSession, user_id: str, new_role: UserRole, current_user_id: str) -> User:
    if user_id == current_user_id:
        raise CANNOT_MODIFY_SELF

    user = await _get_user_or_404(session, user_id)
    if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN and await _count_admins(session) <= 1:
        raise LAST_ADMIN

    old_role = user.role
    user.role = new_role
    await audit_service.record(
        session,
        action=AuditAction.USER_ROLE_CHANGED,
        actor_user_id=current_user_id,
        target_user_id=user.id,
        target_email=user.email,
        detail=f"{old_role.value} -> {new_role.value}",
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_branch(
    session: AsyncSession, user_id: str, branch: str | None, actor_user_id: str
) -> User:
    """No self-modification/last-admin guard like update_role -- branch
    isn't a privilege-escalation vector (it only ever narrows data
    visibility, never grants anything), so there's nothing unsafe about an
    admin changing their own branch scope or every user sharing one."""
    _validate_branch(branch)
    user = await _get_user_or_404(session, user_id)

    old_branch = user.branch
    user.branch = branch
    await audit_service.record(
        session,
        action=AuditAction.USER_BRANCH_CHANGED,
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        target_email=user.email,
        detail=f"{old_branch or 'unrestricted'} -> {branch or 'unrestricted'}",
    )
    await session.commit()
    await session.refresh(user)
    return user


async def reset_password(session: AsyncSession, user_id: str, new_password: str, actor_user_id: str) -> None:
    user = await _get_user_or_404(session, user_id)
    user.hashed_password = hash_password(new_password)
    # A password reset is often a response to a compromised account -- also
    # revoke any refresh tokens already issued to this user, so a stolen
    # refresh cookie can't keep minting access tokens past the reset (see
    # delete_user, which already had to clean these up for its own reasons).
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await audit_service.record(
        session,
        action=AuditAction.USER_PASSWORD_RESET,
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        target_email=user.email,
    )
    await session.commit()


async def delete_user(session: AsyncSession, user_id: str, current_user_id: str) -> None:
    if user_id == current_user_id:
        raise CANNOT_MODIFY_SELF

    user = await _get_user_or_404(session, user_id)
    if user.role == UserRole.ADMIN and await _count_admins(session) <= 1:
        raise LAST_ADMIN

    await audit_service.record(
        session,
        action=AuditAction.USER_DELETED,
        actor_user_id=current_user_id,
        target_user_id=user.id,
        target_email=user.email,
    )
    # No DB-level ON DELETE CASCADE on refresh_tokens.user_id (see
    # models/refresh_token.py) -- clean those up explicitly first so the FK
    # constraint doesn't reject the delete.
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await session.delete(user)
    await session.commit()
