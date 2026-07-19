"""Per-domain queries: a single domain's own totals and which clients
visited it. Backed by raw_events rather than domain_minute_aggregates,
since the aggregate table only tracks per-domain totals across *all*
clients -- it has no per-client breakdown to read a "who visited this site"
list from. Same raw_events dependency (and its retention-window caveat) as
time_spent_service.py.
"""

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
from app.schemas.common import Page, SortOrder
from app.schemas.domains import DomainClientStat, DomainSummary
from app.services.category_inference import effective_category
from app.services.domain_category_service import get_overrides_map


async def get_domain_summary(
    session: AsyncSession, domain: str, since: datetime, until: datetime
) -> DomainSummary:
    blocked_requests = func.coalesce(func.sum(case((RawEvent.blocked, 1), else_=0)), 0)
    total_bytes = func.coalesce(func.sum(RawEvent.bytes), 0)
    distinct_clients = func.count(func.distinct(RawEvent.client_ip))

    total_requests, blocked_total, bytes_total, client_count = (
        await session.execute(
            select(func.count(), blocked_requests, total_bytes, distinct_clients).where(
                RawEvent.domain == domain,
                RawEvent.timestamp >= since,
                RawEvent.timestamp <= until,
            )
        )
    ).one()

    overrides = await get_overrides_map(session)

    return DomainSummary(
        domain=domain,
        total_requests=total_requests,
        blocked_requests=blocked_total,
        total_bytes=bytes_total,
        distinct_client_count=client_count,
        category=effective_category(domain, overrides),
    )


async def get_domain_clients(
    session: AsyncSession,
    domain: str,
    since: datetime,
    until: datetime,
    limit: int,
    offset: int,
    sort_by: str = "visit_count",
    order: SortOrder = SortOrder.DESC,
) -> Page[DomainClientStat]:
    """One row per client that hit this domain in range, with a `user` roll-up
    the same way get_client_summary rolls up users for one IP -- the most
    recently seen value, for display only."""
    visit_count = func.count()
    blocked_count = func.coalesce(func.sum(case((RawEvent.blocked, 1), else_=0)), 0)
    total_bytes = func.coalesce(func.sum(RawEvent.bytes), 0)
    last_visit = func.max(RawEvent.timestamp)
    latest_user = func.max(RawEvent.user)

    conditions = [RawEvent.domain == domain, RawEvent.timestamp >= since, RawEvent.timestamp <= until]

    base_query = (
        select(
            RawEvent.client_ip,
            latest_user.label("user"),
            visit_count.label("visit_count"),
            blocked_count.label("blocked_count"),
            total_bytes.label("total_bytes"),
            last_visit.label("last_visit"),
        )
        .where(*conditions)
        .group_by(RawEvent.client_ip)
    )

    sort_column = {
        "client_ip": RawEvent.client_ip,
        "visit_count": visit_count,
        "blocked_count": blocked_count,
        "total_bytes": total_bytes,
        "last_visit": last_visit,
    }.get(sort_by, visit_count)

    ordered_column = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
    query = base_query.order_by(ordered_column).limit(limit).offset(offset)
    rows = (await session.execute(query)).all()

    count_query = select(func.count()).select_from(
        select(RawEvent.client_ip).where(*conditions).group_by(RawEvent.client_ip).subquery()
    )
    total = (await session.execute(count_query)).scalar_one()

    items = [
        DomainClientStat(
            client_ip=row.client_ip,
            user=row.user,
            visit_count=row.visit_count,
            blocked_count=row.blocked_count,
            total_bytes=row.total_bytes,
            last_visit=row.last_visit,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
