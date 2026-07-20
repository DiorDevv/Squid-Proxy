"""Global (not per-client) queries against RawEvent -- powers /api/events and
is the sibling export_service.py's _fetch_rows should build on top of
instead of hand-rolling its own condition list, so the two query shapes
can't quietly drift apart.
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
from app.schemas.common import Page
from app.schemas.events import EventDetail


def build_event_conditions(
    since: datetime,
    until: datetime,
    blocked_only: bool = False,
    client_ip: str | None = None,
    domain: str | None = None,
    method: str | None = None,
    user: str | None = None,
    search: str | None = None,
) -> list:
    conditions = [RawEvent.timestamp >= since, RawEvent.timestamp <= until]
    if blocked_only:
        conditions.append(RawEvent.blocked.is_(True))
    if client_ip:
        conditions.append(RawEvent.client_ip == client_ip)
    if domain and domain.strip():
        conditions.append(RawEvent.domain.ilike(f"%{domain.strip()}%"))
    if method:
        conditions.append(RawEvent.method == method)
    if user and user.strip():
        conditions.append(RawEvent.user.ilike(f"%{user.strip()}%"))
    if search and search.strip():
        needle = f"%{search.strip()}%"
        conditions.append(
            or_(
                RawEvent.client_ip.ilike(needle),
                RawEvent.domain.ilike(needle),
                RawEvent.url.ilike(needle),
                RawEvent.user.ilike(needle),
            )
        )
    return conditions


async def get_events(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    limit: int,
    offset: int,
    blocked_only: bool = False,
    client_ip: str | None = None,
    domain: str | None = None,
    method: str | None = None,
    user: str | None = None,
    search: str | None = None,
) -> Page[EventDetail]:
    conditions = build_event_conditions(
        since, until, blocked_only, client_ip, domain, method, user, search
    )

    query = (
        select(RawEvent).where(*conditions).order_by(RawEvent.timestamp.desc()).limit(limit).offset(offset)
    )
    rows = (await session.execute(query)).scalars().all()

    count_query = select(func.count()).select_from(RawEvent).where(*conditions)
    total = (await session.execute(count_query)).scalar_one()

    items = [EventDetail.from_raw_event(row) for row in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)
