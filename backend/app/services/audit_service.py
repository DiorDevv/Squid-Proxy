"""Records and reads back admin user-management actions (see
app/services/user_service.py for the write side)."""

from sqlalchemy import func, select
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
    target_user_id: str | None = None,
    target_email: str | None = None,
    detail: str | None = None,
) -> None:
    """Adds an audit row to `session` without committing -- callers add this
    to the same transaction as the change it describes, so the two can
    never disagree (an audited action that didn't happen, or vice versa)."""
    actor_email = await _resolve_actor_email(session, actor_user_id)
    session.add(
        AuditLogEntry(
            action=action,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_user_id=target_user_id,
            target_email=target_email,
            detail=detail,
        )
    )


async def list_entries(session: AsyncSession, limit: int, offset: int) -> Page[AuditLogEntryOut]:
    query = (
        select(AuditLogEntry).order_by(AuditLogEntry.created_at.desc()).limit(limit).offset(offset)
    )
    rows = (await session.execute(query)).scalars().all()
    total = (await session.execute(select(func.count()).select_from(AuditLogEntry))).scalar_one()

    items = [
        AuditLogEntryOut(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            actor_email=row.actor_email,
            target_email=row.target_email,
            detail=row.detail,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
