"""Records and reads back admin user-management actions (see
app/services/user_service.py for the write side)."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLogEntry
from app.models.user import User
from app.schemas.audit import AuditLogEntryOut
from app.schemas.common import Page


async def _resolve_actor_email(session: AsyncSession, actor_user_id: str) -> str:
    email = (
        await session.execute(select(User.email).where(User.id == actor_user_id))
    ).scalar_one_or_none()
    return email or "unknown"


async def record(
    session: AsyncSession,
    *,
    action: AuditAction,
    actor_user_id: str,
    branch: str | None = None,
    target_user_id: str | None = None,
    target_email: str | None = None,
    detail: str | None = None,
) -> None:
    """Adds an audit row to `session` without committing -- callers add this
    to the same transaction as the change it describes, so the two can
    never disagree (an audited action that didn't happen, or vice versa).

    `branch` tags which branch this action is scoped to, mirroring whatever
    branch value the caller already resolved for the change itself (e.g. the
    target user's branch, the export job's branch). Leave it unset (None)
    only for actions with no branch dimension or with unrestricted reach --
    see AuditLogEntry.branch and list_entries for how that's read back."""
    actor_email = await _resolve_actor_email(session, actor_user_id)
    session.add(
        AuditLogEntry(
            action=action,
            branch=branch,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_user_id=target_user_id,
            target_email=target_email,
            detail=detail,
        )
    )


async def list_entries(
    session: AsyncSession, limit: int, offset: int, branch: str | None = None
) -> Page[AuditLogEntryOut]:
    """`branch` follows the same contract as api.deps.resolve_branch: None
    (an unrestricted caller, or no branch requested) returns every entry.
    A concrete branch returns that branch's entries *plus* every entry with
    no branch of its own (see AuditLogEntry.branch) -- an action that wasn't
    confined to one branch is visible to everyone, only branch-confined
    entries for another branch are held back. Route callers must resolve
    `branch` through api.deps.resolve_branch first so a branch-scoped admin
    can never pass an arbitrary value here."""
    query = select(AuditLogEntry)
    count_query = select(func.count()).select_from(AuditLogEntry)
    if branch is not None:
        scope = or_(AuditLogEntry.branch.is_(None), AuditLogEntry.branch == branch)
        query = query.where(scope)
        count_query = count_query.where(scope)

    query = query.order_by(AuditLogEntry.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(query)).scalars().all()
    total = (await session.execute(count_query)).scalar_one()

    items = [
        AuditLogEntryOut(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            branch=row.branch,
            actor_email=row.actor_email,
            target_email=row.target_email,
            detail=row.detail,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
