"""Per-client (IP + user) queries: listing, sorting, and activity history.

The clients listing reads from ClientMinuteAggregate and ClientHourlyAggregate
combined (see client_bucket_rows); "last_activity" is therefore
minute-granular for recent activity and hour-granular for anything old
enough to have been rolled up (see retention.py). Full per-event detail for
a single client comes from raw_events instead, which does have
to-the-second timestamps.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.raw_event import RawEvent
from app.schemas.clients import ClientActivityEvent, ClientSummary
from app.schemas.common import Page, SortOrder


def client_bucket_rows(
    since: datetime,
    until: datetime,
    client_ip: str | None = None,
    search: str | None = None,
):
    """A client_ip/user/bucket_ts/counts subquery unioning
    client_minute_aggregates and client_hourly_aggregates over the same
    [since, until] range. Safe to just UNION both unconditionally rather
    than routing to "the right table" by cutoff date: RetentionJob's rollup
    always deletes a minute row in the same transaction it writes the
    corresponding hourly row, so the two tables never cover the same instant
    for the same client -- there's nothing to double-count.
    """
    needle = f"%{search.strip()}%" if search and search.strip() else None

    def _branch(model):
        if model is ClientHourlyAggregate:
            # Hourly rows are truncated to the top of the hour and each one
            # represents the whole [bucket_ts, bucket_ts + 1h) window. A
            # naive `bucket_ts >= since AND bucket_ts <= until` comparison
            # against that truncated timestamp silently drops a boundary
            # hour that's only partially in range (when `since` falls after
            # its start) or fully includes one that's only partially in
            # range (when `until` falls before its end) -- and `since`/
            # `until` are essentially never hour-aligned in practice. Use
            # interval overlap instead, so a boundary hour is included
            # whenever any slice of it falls inside [since, until]: this can
            # only ever pull in a little extra (already-coarse, per
            # ARCHITECTURE.md) boundary data, never silently drop real
            # traffic, which matters more for a compliance tool.
            conditions = [model.bucket_ts <= until, model.bucket_ts > since - timedelta(hours=1)]
        else:
            conditions = [model.bucket_ts >= since, model.bucket_ts <= until]
        if client_ip is not None:
            conditions.append(model.client_ip == client_ip)
        if needle is not None:
            conditions.append(or_(model.client_ip.ilike(needle), model.user.ilike(needle)))
        return select(
            model.client_ip.label("client_ip"),
            model.user.label("user"),
            model.request_count.label("request_count"),
            model.blocked_count.label("blocked_count"),
            model.total_bytes.label("total_bytes"),
            model.bucket_ts.label("bucket_ts"),
        ).where(*conditions)

    return union_all(_branch(ClientMinuteAggregate), _branch(ClientHourlyAggregate)).subquery()


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
    combined = client_bucket_rows(since, until, search=search)

    total_requests = func.sum(combined.c.request_count)
    blocked_requests = func.sum(combined.c.blocked_count)
    total_bytes = func.sum(combined.c.total_bytes)
    last_activity = func.max(combined.c.bucket_ts)

    base_query = select(
        combined.c.client_ip,
        combined.c.user,
        total_requests.label("total_requests"),
        blocked_requests.label("blocked_requests"),
        total_bytes.label("total_bytes"),
        last_activity.label("last_activity"),
    ).group_by(combined.c.client_ip, combined.c.user)

    sort_column = {
        "client_ip": combined.c.client_ip,
        "user": combined.c.user,
        "total_requests": total_requests,
        "blocked_requests": blocked_requests,
        "total_bytes": total_bytes,
        "last_activity": last_activity,
    }.get(sort_by, total_requests)

    ordered_column = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
    query = base_query.order_by(ordered_column).limit(limit).offset(offset)

    rows = (await session.execute(query)).all()

    count_query = select(func.count()).select_from(
        select(combined.c.client_ip, combined.c.user)
        .group_by(combined.c.client_ip, combined.c.user)
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
    combined = client_bucket_rows(since, until, client_ip=client_ip)

    total_requests = func.coalesce(func.sum(combined.c.request_count), 0)
    blocked_requests = func.coalesce(func.sum(combined.c.blocked_count), 0)
    total_bytes = func.coalesce(func.sum(combined.c.total_bytes), 0)
    last_activity = func.max(combined.c.bucket_ts)
    latest_user = func.max(combined.c.user)

    row = (
        await session.execute(select(total_requests, blocked_requests, total_bytes, last_activity, latest_user))
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
