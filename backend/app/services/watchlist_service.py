"""CRUD for watchlist entries (see app/models/watchlist_entry.py). The
matching/alerting side lives in app/services/watchlist_monitor.py.
"""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist_entry import WatchlistEntry, WatchlistTargetType
from app.schemas.watchlist import WatchlistEntryOut


class WatchlistConflict(Exception):
    """That (target_type, value, branch) is already watched."""


def normalize_value(target_type: WatchlistTargetType, value: str) -> str:
    value = value.strip()
    if target_type in (WatchlistTargetType.DOMAIN, WatchlistTargetType.USER):
        return value.lower()
    return value


def _to_out(row: WatchlistEntry) -> WatchlistEntryOut:
    return WatchlistEntryOut(
        id=row.id,
        target_type=row.target_type,
        value=row.value,
        note=row.note,
        branch=row.branch,
        active=row.active,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        last_alerted_at=row.last_alerted_at,
    )


async def list_entries(session: AsyncSession, branch: str | None) -> list[WatchlistEntryOut]:
    """A branch-scoped admin sees the "any branch" entries plus their own
    branch's; an unrestricted admin sees everything."""
    query = select(WatchlistEntry)
    if branch is not None:
        query = query.where(or_(WatchlistEntry.branch == "", WatchlistEntry.branch == branch))
    query = query.order_by(WatchlistEntry.created_at.desc())
    rows = (await session.execute(query)).scalars().all()
    return [_to_out(row) for row in rows]


async def create_entry(
    session: AsyncSession,
    target_type: WatchlistTargetType,
    value: str,
    note: str | None,
    branch: str,
    created_by: str,
) -> WatchlistEntryOut:
    row = WatchlistEntry(
        target_type=target_type,
        value=normalize_value(target_type, value),
        note=note,
        branch=branch,
        created_by=created_by,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise WatchlistConflict from exc
    await session.refresh(row)
    return _to_out(row)


async def get_entry(session: AsyncSession, entry_id: str) -> WatchlistEntry | None:
    return (
        await session.execute(select(WatchlistEntry).where(WatchlistEntry.id == entry_id))
    ).scalar_one_or_none()


async def set_active(session: AsyncSession, entry_id: str, active: bool) -> WatchlistEntryOut | None:
    row = await get_entry(session, entry_id)
    if row is None:
        return None
    row.active = active
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


async def delete_entry(session: AsyncSession, entry_id: str) -> bool:
    row = await get_entry(session, entry_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
