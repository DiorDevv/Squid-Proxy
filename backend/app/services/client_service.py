"""Per-client (IP + user) queries: listing, sorting, and activity history.

The clients listing reads from ClientMinuteAggregate (fast, pre-aggregated);
"last_activity" is therefore minute-granular, not to-the-second. Full
per-event detail for a single client comes from raw_events instead, which
does have to-the-second timestamps.
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.raw_event import RawEvent
from app.schemas.clients import ClientActivityEvent, ClientSummary
from app.schemas.common import Page, SortOrder


async def list_clients(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    limit: int,
    offset: int,
    sort_by: str = "total_requests",
    order: SortOrder = SortOrder.DESC,
    search: str | None = None,
) -> Page[ClientSummary]:
    """`search`, when given, filters server-side (case-insensitive substring
    match on IP or user) *before* pagination -- so `total`/`offset` and the
    rows actually returned always agree, unlike a client that fetches one
    page and then filters it locally against a total that was computed
    without the filter applied."""
    total_requests = func.sum(ClientMinuteAggregate.request_count)
    blocked_requests = func.sum(ClientMinuteAggregate.blocked_count)
    total_bytes = func.sum(ClientMinuteAggregate.total_bytes)
    last_activity = func.max(ClientMinuteAggregate.bucket_ts)

    search_conditions = []
    if search and search.strip():
        needle = f"%{search.strip()}%"
        search_conditions.append(
            or_(
                ClientMinuteAggregate.client_ip.ilike(needle),
                ClientMinuteAggregate.user.ilike(needle),
            )
        )

    base_query = (
        select(
            ClientMinuteAggregate.client_ip,
            ClientMinuteAggregate.user,
            total_requests.label("total_requests"),
            blocked_requests.label("blocked_requests"),
            total_bytes.label("total_bytes"),
            last_activity.label("last_activity"),
        )
        .where(
            ClientMinuteAggregate.bucket_ts >= since,
            ClientMinuteAggregate.bucket_ts <= until,
            *search_conditions,
        )
        .group_by(ClientMinuteAggregate.client_ip, ClientMinuteAggregate.user)
    )

    sort_column = {
        "client_ip": ClientMinuteAggregate.client_ip,
        "user": ClientMinuteAggregate.user,
        "total_requests": total_requests,
        "blocked_requests": blocked_requests,
        "total_bytes": total_bytes,
        "last_activity": last_activity,
    }.get(sort_by, total_requests)

    ordered_column = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
    query = base_query.order_by(ordered_column).limit(limit).offset(offset)

    rows = (await session.execute(query)).all()

    count_query = select(func.count()).select_from(
        select(ClientMinuteAggregate.client_ip, ClientMinuteAggregate.user)
        .where(
            ClientMinuteAggregate.bucket_ts >= since,
            ClientMinuteAggregate.bucket_ts <= until,
            *search_conditions,
        )
        .group_by(ClientMinuteAggregate.client_ip, ClientMinuteAggregate.user)
        .subquery()
    )
    total = (await session.execute(count_query)).scalar_one()

    items = [
        ClientSummary(
            client_ip=row.client_ip,
            user=row.user,
            total_requests=row.total_requests,
            blocked_requests=row.blocked_requests,
            total_bytes=row.total_bytes,
            last_activity=row.last_activity,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


async def get_client_summary(
    session: AsyncSession, client_ip: str, since: datetime, until: datetime
) -> ClientSummary:
    """Rolls up all `user` values seen for this IP within the range into one
    summary row (a client detail page is keyed by IP alone) -- `user` in the
    result is just the most recently seen one, for display only."""
    total_requests = func.coalesce(func.sum(ClientMinuteAggregate.request_count), 0)
    blocked_requests = func.coalesce(func.sum(ClientMinuteAggregate.blocked_count), 0)
    total_bytes = func.coalesce(func.sum(ClientMinuteAggregate.total_bytes), 0)
    last_activity = func.max(ClientMinuteAggregate.bucket_ts)
    latest_user = func.max(ClientMinuteAggregate.user)

    row = (
        await session.execute(
            select(total_requests, blocked_requests, total_bytes, last_activity, latest_user).where(
                ClientMinuteAggregate.client_ip == client_ip,
                ClientMinuteAggregate.bucket_ts >= since,
                ClientMinuteAggregate.bucket_ts <= until,
            )
        )
    ).one()
    requests_total, blocked_total, bytes_total, activity, user = row

    return ClientSummary(
        client_ip=client_ip,
        user=user,
        total_requests=requests_total,
        blocked_requests=blocked_total,
        total_bytes=bytes_total,
        last_activity=activity,
    )


async def get_client_activity(
    session: AsyncSession,
    client_ip: str,
    since: datetime,
    until: datetime,
    limit: int,
    offset: int,
    blocked_only: bool = False,
    domain: str | None = None,
    method: str | None = None,
) -> Page[ClientActivityEvent]:
    conditions = [
        RawEvent.client_ip == client_ip,
        RawEvent.timestamp >= since,
        RawEvent.timestamp <= until,
    ]
    if blocked_only:
        conditions.append(RawEvent.blocked.is_(True))
    if domain and domain.strip():
        conditions.append(RawEvent.domain.ilike(f"%{domain.strip()}%"))
    if method:
        conditions.append(RawEvent.method == method)

    query = (
        select(RawEvent).where(*conditions).order_by(RawEvent.timestamp.desc()).limit(limit).offset(offset)
    )
    rows = (await session.execute(query)).scalars().all()

    count_query = select(func.count()).select_from(RawEvent).where(*conditions)
    total = (await session.execute(count_query)).scalar_one()

    items = [
        ClientActivityEvent(
            id=row.id,
            timestamp=row.timestamp,
            method=row.method,
            url=row.url,
            domain=row.domain,
            action=row.action,
            status_code=row.status_code,
            bytes=row.bytes,
            blocked=row.blocked,
        )
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
