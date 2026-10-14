"""User management: list/create/edit/role/branch/password reset/deactivate.

There is no self-service signup or password-reset-by-email flow -- this is
an internal security tool whose accounts are provisioned by an admin.

Who may do what:
  - A super admin manages every account, including other super admins.
    Super admins are always unrestricted (branch is None).
  - An admin manages *viewer* accounts in their own scope only (their
    branch, or every branch for an unrestricted admin) -- create, edit,
    reset password, deactivate, unlock, end sessions. Never roles, never
    another admin/auditor/super admin.

Security rules:
  - Admins never choose passwords. Creating an account or resetting its
    password generates a one-time temporary password (returned once,
    never stored or logged) that must be changed at first sign-in
    (must_change_password, enforced by api/deps.get_current_user).
  - Accounts are deactivated, never deleted, so the audit trail keeps
    pointing at a real row. Deactivating, resetting a password, or
    changing role/branch ends every session of that account at once.
  - Nobody changes their own role, branch or active state here, and the
    last active super admin can't be demoted or deactivated.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core import password_policy
from app.core import permissions as permission_catalog
from app.core.branch_scope import as_scope, normalize_branches, scope_tag, scope_within
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.audit_log import AuditAction
from app.models.refresh_token import RefreshToken
from app.models.totp_recovery_code import TotpRecoveryCode
from app.models.user import PasswordHistory, User, UserRole
from app.services import audit_service, session_service

USERNAME_TAKEN = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="A user with this username already exists."
)
EMAIL_TAKEN = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists."
)
USER_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
CANNOT_MODIFY_SELF = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="You cannot change your own role, branch or account status here -- use your profile page "
    "or ask another super admin.",
)
LAST_SUPERADMIN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="This is the last active super admin -- make someone else a super admin first.",
)
VIEWERS_ONLY = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Admins can only manage viewer accounts. Ask a super admin.",
)
ROLES_SUPERADMIN_ONLY = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Only a super admin can change roles."
)
SUPERADMIN_UNRESTRICTED = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="A super admin always has access to every branch.",
)
NO_BRANCH_ACCESS = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You do not have access to this branch.",
)


SUPERADMIN_NO_EXPIRY = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="A super admin account can't have an end date -- it could lock everyone out.",
)


def _enforce_actor_branches(
    requested: tuple[str, ...] | None, actor_branches: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    """Same contract as api.deps.resolve_branch, for granting a scope: an
    unrestricted actor passes `requested` through unchanged; a
    branch-limited actor gets their own branches substituted if they asked
    for none (they can never grant unrestricted access), and a 403 if they
    asked for any branch outside their own -- this is what stops a
    branch-limited admin from creating a user in (or moving one to) another
    branch."""
    if actor_branches is None:
        return requested
    if requested is None:
        return actor_branches
    if not set(requested) <= set(actor_branches):
        raise NO_BRANCH_ACCESS
    return requested


def _validate_branches(branches: tuple[str, ...] | None) -> None:
    """None (unrestricted) always passes -- only concrete branches are
    checked against the configured set, so a typo here can't silently lock
    a user out of everything instead of failing loudly at creation/update
    time."""
    if branches is None:
        return
    valid_branches = {source.branch for source in get_settings().effective_log_sources}
    unknown = [b for b in branches if b not in valid_branches]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown branch {unknown[0]!r}. "
            f"Configured branches: {', '.join(sorted(valid_branches))}.",
        )


def _normalize_permissions(permissions: list[str] | None) -> list[str] | None:
    try:
        return permission_catalog.normalize(permissions)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _check_grantable(permissions: list[str] | None, role: UserRole, actor: CurrentUser) -> None:
    """Nobody hands out a permission they don't hold themselves -- an admin
    stripped of "export" can't give a viewer "export"."""
    granted = permission_catalog.effective(role.value, permissions)
    beyond = sorted(granted - actor.permissions)
    if beyond:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You can't grant permissions you don't have: {', '.join(beyond)}.",
        )


def _describe_permissions(permissions: list[str] | None) -> str:
    return "role default" if permissions is None else (",".join(permissions) or "none")


def _as_utc(moment: datetime | None) -> datetime | None:
    """A timestamp without a zone is taken as UTC (the frontend sends ISO
    strings with "Z", but a hand-made API call might not)."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


def _describe_expiry(expires_at: datetime | None) -> str:
    return expires_at.isoformat() if expires_at is not None else "never"


def check_password_policy(password: str, username: str) -> None:
    if problems := password_policy.password_problems(password, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet the requirements: " + "; ".join(problems) + ".",
        )


def _in_scope(user: User, actor: CurrentUser) -> bool:
    """A branch-limited actor reaches only accounts whose whole scope lies
    inside its own branches (never an unrestricted account)."""
    return scope_within(as_scope(user.branch_scope), actor.branches)


def _require_manageable(user: User, actor: CurrentUser) -> None:
    """404 for a user outside the actor's branch (doesn't confirm the
    account exists at all), 403 for an admin reaching past viewers."""
    if not _in_scope(user, actor):
        raise USER_NOT_FOUND
    if not actor.is_superadmin and user.role != UserRole.VIEWER:
        raise VIEWERS_ONLY


def _not_self(user: User, actor: CurrentUser) -> None:
    if user.id == actor.user_id:
        raise CANNOT_MODIFY_SELF


async def _get_user_or_404(session: AsyncSession, user_id: str) -> User:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise USER_NOT_FOUND
    return user


async def _keep_a_superadmin(session: AsyncSession, user: User) -> None:
    """Call before `user` stops being an active super admin."""
    if user.role != UserRole.SUPERADMIN or not user.is_active:
        return
    others = (
        await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.SUPERADMIN, User.is_active.is_(True), User.id != user.id)
        )
    ).scalar_one()
    if not others:
        raise LAST_SUPERADMIN


async def _check_email_free(session: AsyncSession, email: str | None, exclude_id: str | None = None) -> None:
    if email is None:
        return
    query = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    if (await session.execute(query)).scalar_one_or_none() is not None:
        raise EMAIL_TAKEN


async def _set_password(session: AsyncSession, user: User, new_hash: str, *, must_change: bool) -> None:
    """The outgoing hash moves into history (newest HISTORY kept), the new
    one is set, and the account's sessions are dealt with by the caller."""
    session.add(PasswordHistory(user_id=user.id, hashed_password=user.hashed_password))
    await session.flush()
    keep = (
        (
            await session.execute(
                select(PasswordHistory.id)
                .where(PasswordHistory.user_id == user.id)
                .order_by(PasswordHistory.created_at.desc())
                .limit(password_policy.HISTORY)
            )
        )
        .scalars()
        .all()
    )
    await session.execute(
        delete(PasswordHistory).where(PasswordHistory.user_id == user.id, PasswordHistory.id.not_in(keep))
    )
    now = datetime.now(UTC)
    user.hashed_password = new_hash
    user.must_change_password = must_change
    user.password_changed_at = now
    user.updated_at = now


async def _end_all_sessions(session: AsyncSession, user: User) -> int:
    # token_version kills live access tokens (including any minted before
    # sessions existed); revoking the refresh tokens stops new ones.
    user.token_version += 1
    return await session_service.revoke(session, user.id)


# --- Reads -------------------------------------------------------------------


async def list_users(session: AsyncSession, actor: CurrentUser) -> list[User]:
    query = select(User).order_by(User.is_active.desc(), User.username)
    users = list((await session.execute(query)).scalars().all())
    # Branch scopes live in a JSON list, so the (small) user table is
    # filtered here rather than in SQL.
    return [u for u in users if _in_scope(u, actor)]


async def session_counts(session: AsyncSession, user_ids: list[str]) -> dict[str, int]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(RefreshToken.user_id, func.count())
        .where(
            RefreshToken.user_id.in_(user_ids),
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .group_by(RefreshToken.user_id)
    )
    return {user_id: count for user_id, count in rows.all()}


async def get_manageable_user(session: AsyncSession, user_id: str, actor: CurrentUser) -> User:
    user = await _get_user_or_404(session, user_id)
    _require_manageable(user, actor)
    return user


# --- Writes ------------------------------------------------------------------


async def create_user(
    session: AsyncSession,
    actor: CurrentUser,
    *,
    username: str,
    role: UserRole,
    full_name: str = "",
    note: str | None = None,
    email: str | None = None,
    branch: str | None = None,
    branches: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[User, str]:
    """Returns the new user and its one-time temporary password. `branch`
    is the single-branch shorthand for `branches`; `permissions` None means
    the role's defaults."""
    username = password_policy.normalize_username(username)
    if problem := password_policy.username_problem(username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)
    if not actor.is_superadmin and role != UserRole.VIEWER:
        raise VIEWERS_ONLY
    scope = normalize_branches(branches if branches is not None else ([branch] if branch else None))
    permissions = _normalize_permissions(permissions)
    expires_at = _as_utc(expires_at)
    if role == UserRole.SUPERADMIN:
        if scope is not None:
            raise SUPERADMIN_UNRESTRICTED
        if expires_at is not None:
            raise SUPERADMIN_NO_EXPIRY
        permissions = None
    else:
        scope = _enforce_actor_branches(scope, actor.branches)
        _validate_branches(scope)
        _check_grantable(permissions, role, actor)

    if (await session.execute(select(User.id).where(User.username == username))).scalar_one_or_none():
        raise USERNAME_TAKEN
    await _check_email_free(session, email)

    temp_password = password_policy.generate_password()
    user = User(
        username=username,
        full_name=full_name.strip(),
        note=(note or "").strip() or None,
        email=email,
        hashed_password=hash_password(temp_password),
        role=role,
        branches=list(scope) if scope is not None else None,
        permissions=permissions,
        expires_at=expires_at,
        must_change_password=True,
        created_by=actor.username,
    )
    session.add(user)
    await session.flush()
    detail = f"role={role.value}, branch={scope_tag(as_scope(scope)) or 'unrestricted'}"
    if permissions is not None:
        detail += f", permissions={_describe_permissions(permissions)}"
    if expires_at is not None:
        detail += f", expires_at={_describe_expiry(expires_at)}"
    await audit_service.record(
        session,
        action=AuditAction.USER_CREATED,
        actor_user_id=actor.user_id,
        branch=as_scope(scope),
        target_user_id=user.id,
        target_email=username,
        detail=detail,
    )
    await session.commit()
    await session.refresh(user)
    return user, temp_password


_UNSET = object()


async def update_profile(
    session: AsyncSession,
    user_id: str,
    actor: CurrentUser,
    *,
    full_name: str | None = None,
    note: object = _UNSET,
    email: object = _UNSET,
) -> User:
    """Descriptive fields only (no effect on access): full name, note,
    contact email. `note`/`email` distinguish "not sent" from "cleared"."""
    user = await get_manageable_user(session, user_id, actor)
    changes: dict[str, tuple[object, object]] = {}
    if full_name is not None and full_name.strip() != user.full_name:
        changes["full_name"] = (user.full_name, full_name.strip())
    if note is not _UNSET:
        new_note = (str(note) if note is not None else "").strip() or None
        if new_note != user.note:
            changes["note"] = (user.note, new_note)
    if email is not _UNSET and email != user.email:
        await _check_email_free(session, email if isinstance(email, str) else None, exclude_id=user.id)
        changes["email"] = (user.email, email)
    if not changes:
        return user

    for field, (_, new) in changes.items():
        setattr(user, field, new)
    user.updated_at = datetime.now(UTC)
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATED,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
        detail="; ".join(f"{k}: {old or '-'} -> {new or '-'}" for k, (old, new) in changes.items()),
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_role(session: AsyncSession, user_id: str, new_role: UserRole, actor: CurrentUser) -> User:
    if not actor.is_superadmin:
        raise ROLES_SUPERADMIN_ONLY
    user = await _get_user_or_404(session, user_id)
    _not_self(user, actor)
    if user.role == new_role:
        return user
    if new_role != UserRole.SUPERADMIN:
        await _keep_a_superadmin(session, user)

    old_role = user.role
    user.role = new_role
    old_branch = user.branch
    if new_role == UserRole.SUPERADMIN:
        # Always unrestricted, every permission, no end date.
        user.branches = None
        user.permissions = None
        user.expires_at = None
    user.updated_at = datetime.now(UTC)
    # End every existing session of this account: the new role must be in
    # force on the next request, and the frontend needs a fresh token so
    # its own role-gated UI matches what the API will now allow.
    user.token_version += 1
    detail = f"{old_role.value} -> {new_role.value}"
    if old_branch != user.branch:
        detail += f" (branch {old_branch} -> unrestricted)"
    await audit_service.record(
        session,
        action=AuditAction.USER_ROLE_CHANGED,
        actor_user_id=actor.user_id,
        branch=old_branch,
        target_user_id=user.id,
        target_email=user.username,
        detail=detail,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_branches(
    session: AsyncSession, user_id: str, branches: list[str] | None, actor: CurrentUser
) -> User:
    """Branch scope is a privilege-escalation vector: api.deps.resolve_branch
    treats an unrestricted account as seeing everything, so a branch-limited
    admin may only set a viewer's branches within their own
    (_enforce_actor_branches), and nobody changes their own. None or []
    means unrestricted."""
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    if user.role == UserRole.SUPERADMIN:
        raise SUPERADMIN_UNRESTRICTED
    scope = _enforce_actor_branches(normalize_branches(branches), actor.branches)
    _validate_branches(scope)
    if scope == user.branch_scope:
        return user

    old_scope = as_scope(user.branch_scope)
    user.branches = list(scope) if scope is not None else None
    user.updated_at = datetime.now(UTC)
    # Same reasoning as update_role: force a re-login so the new branch
    # scope takes effect immediately and consistently on both sides.
    user.token_version += 1
    await audit_service.record(
        session,
        action=AuditAction.USER_BRANCH_CHANGED,
        actor_user_id=actor.user_id,
        # Tagged with the *old* scope: tagging the origin means the branch
        # losing the user still sees the departure.
        branch=old_scope,
        target_user_id=user.id,
        target_email=user.username,
        detail=f"{scope_tag(old_scope) or 'unrestricted'} -> {scope_tag(as_scope(scope)) or 'unrestricted'}",
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_branch(session: AsyncSession, user_id: str, branch: str | None, actor: CurrentUser) -> User:
    """Single-branch shorthand for update_branches."""
    return await update_branches(session, user_id, [branch] if branch else None, actor)


async def update_permissions(
    session: AsyncSession, user_id: str, permissions: list[str] | None, actor: CurrentUser
) -> User:
    """None restores the role's defaults; a list is the exact set. Granting
    is capped by the actor's own permissions (_check_grantable)."""
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    if user.role == UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A super admin always has every permission."
        )
    permissions = _normalize_permissions(permissions)
    _check_grantable(permissions, user.role, actor)
    if permissions == user.permissions:
        return user

    old = user.permissions
    user.permissions = permissions
    user.updated_at = datetime.now(UTC)
    # Permissions are read from the live row on every request already; the
    # bump makes the frontend fetch a fresh profile so its menus match.
    user.token_version += 1
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATED,
        actor_user_id=actor.user_id,
        branch=as_scope(user.branch_scope),
        target_user_id=user.id,
        target_email=user.username,
        detail=f"permissions: {_describe_permissions(old)} -> {_describe_permissions(permissions)}",
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_expiry(
    session: AsyncSession, user_id: str, expires_at: datetime | None, actor: CurrentUser
) -> User:
    """None removes the end date. A moment already past cuts the account off
    on its next request (api.deps._authenticate)."""
    expires_at = _as_utc(expires_at)
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    if user.role == UserRole.SUPERADMIN and expires_at is not None:
        raise SUPERADMIN_NO_EXPIRY
    if expires_at == user.expires_at:
        return user

    old = user.expires_at
    user.expires_at = expires_at
    user.updated_at = datetime.now(UTC)
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATED,
        actor_user_id=actor.user_id,
        branch=as_scope(user.branch_scope),
        target_user_id=user.id,
        target_email=user.username,
        detail=f"expires_at: {_describe_expiry(old)} -> {_describe_expiry(expires_at)}",
    )
    await session.commit()
    await session.refresh(user)
    return user

async def reset_password(session: AsyncSession, user_id: str, actor: CurrentUser) -> tuple[User, str]:
    """Issues a new one-time temporary password. Usually a compromise
    response, so every session of the account ends with it."""
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    temp_password = password_policy.generate_password()
    await _set_password(session, user, hash_password(temp_password), must_change=True)
    closed = await _end_all_sessions(session, user)
    await audit_service.record(
        session,
        action=AuditAction.USER_PASSWORD_RESET,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
        detail=f"sessions_closed={closed}",
    )
    await session.commit()
    await session.refresh(user)
    return user, temp_password


async def set_active(session: AsyncSession, user_id: str, active: bool, actor: CurrentUser) -> User:
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    if user.is_active == active:
        return user
    detail = None
    if not active:
        await _keep_a_superadmin(session, user)
        closed = await _end_all_sessions(session, user)
        detail = f"sessions_closed={closed}"
    user.is_active = active
    user.updated_at = datetime.now(UTC)
    await audit_service.record(
        session,
        action=AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
        detail=detail,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def record_unlock(session: AsyncSession, user: User, actor: CurrentUser) -> None:
    """The throttle itself lives in app.state (see routes/users.unlock_user);
    this only writes the audit entry."""
    await audit_service.record(
        session,
        action=AuditAction.USER_UNLOCKED,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
    )
    await session.commit()


async def revoke_sessions(
    session: AsyncSession, user_id: str, actor: CurrentUser, session_id: str | None = None
) -> int:
    user = await get_manageable_user(session, user_id, actor)
    closed = await session_service.revoke(
        session, user.id, session_id=session_id, keep_session_id=actor.session_id
    )
    await audit_service.record(
        session,
        action=AuditAction.USER_SESSIONS_REVOKED,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
        detail=f"closed={closed}" + (f", session={session_id}" if session_id else ""),
    )
    await session.commit()
    return closed


async def reset_totp(session: AsyncSession, user_id: str, actor: CurrentUser) -> User:
    """For a user who lost their authenticator and their recovery codes --
    they can sign in with the password alone and set 2FA up again."""
    user = await get_manageable_user(session, user_id, actor)
    _not_self(user, actor)
    if not user.totp_enabled and user.totp_secret is None:
        return user
    user.totp_secret = None
    user.totp_enabled = False
    user.updated_at = datetime.now(UTC)
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user.id))
    await audit_service.record(
        session,
        action=AuditAction.USER_TOTP_RESET,
        actor_user_id=actor.user_id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def change_own_password(
    session: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    keep_session_id: str | None,
) -> int:
    """The caller has already verified current_password (with throttling).
    Other sessions are closed -- the old password may have leaked -- and
    the number closed is returned."""
    if new_password == current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must differ from the current one.",
        )
    check_password_policy(new_password, user.username)
    history = (
        (
            await session.execute(
                select(PasswordHistory.hashed_password)
                .where(PasswordHistory.user_id == user.id)
                .order_by(PasswordHistory.created_at.desc())
                .limit(password_policy.HISTORY - 1)
            )
        )
        .scalars()
        .all()
    )
    if any(verify_password(new_password, old_hash) for old_hash in history):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This password was used recently -- choose one different from your last "
            f"{password_policy.HISTORY}.",
        )
    was_temporary = user.must_change_password
    await _set_password(session, user, hash_password(new_password), must_change=False)
    closed = await session_service.revoke(session, user.id, keep_session_id=keep_session_id)
    await audit_service.record(
        session,
        action=AuditAction.USER_PASSWORD_CHANGED,
        actor_user_id=user.id,
        branch=user.branch,
        target_user_id=user.id,
        target_email=user.username,
        detail=f"first_login={was_temporary}, sessions_closed={closed}",
    )
    await session.commit()
    return closed
