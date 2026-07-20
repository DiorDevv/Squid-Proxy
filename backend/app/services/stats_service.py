"""Read-side aggregate queries. Always reads from the database, never the
ring buffer, so 1h/24h/7d ranges (and custom from_ts/to_ts windows) share one
consistent source of truth."""

from collections import defaultdict
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.schemas.common import Granularity, RangeParam
from app.schemas.domains import CategoryStat, DomainStat
from app.schemas.summary import SummaryResponse
from app.schemas.timeseries import TimeseriesPoint, TimeseriesResponse
from app.services.category_inference import effective_category
from app.services.client_service import client_bucket_rows
from app.services.domain_category_service import get_overrides_map


async def get_summary(
    session: AsyncSession, since: datetime, until: datetime, range_param: RangeParam | None
) -> SummaryResponse:
    totals_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(MinuteAggregate.total_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.blocked_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.allowed_requests), 0),
            ).where(MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until)
        )
    ).one()
    total_requests, blocked_requests, allowed_requests = totals_row

    # Reads client_minute_aggregates and client_hourly_aggregates combined
    # (see client_bucket_rows) -- a range extending past the rollup cutoff
    # (retention.py) would otherwise silently undercount, since older
    # activity has been compressed into the hourly table and the source
    # minute rows deleted.
    combined = client_bucket_rows(since, until)

    active_clients = (
        await session.execute(select(func.count(func.distinct(combined.c.client_ip))))
    ).scalar_one()

    active_users = (
        await session.execute(
            select(func.count(func.distinct(combined.c.user))).where(combined.c.user.is_not(None))
        )
    ).scalar_one()

    return SummaryResponse(
        range=range_param,
        since=since,
        until=until,
        total_requests=total_requests,
        blocked_requests=blocked_requests,
        allowed_requests=allowed_requests,
        active_client_count=active_clients,
        active_user_count=active_users,
    )


async def get_timeseries(
    session: AsyncSession, since: datetime, until: datetime, granularity: Granularity
) -> TimeseriesResponse:
    rows = (
        await session.execute(
            select(MinuteAggregate)
            .where(MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until)
            .order_by(MinuteAggregate.bucket_ts)
        )
    ).scalars().all()

    if granularity == Granularity.MINUTE:
        points = [
            TimeseriesPoint(
                bucket_ts=row.bucket_ts,
                total_requests=row.total_requests,
                blocked_requests=row.blocked_requests,
                allowed_requests=row.allowed_requests,
            )
            for row in rows
        ]
        return TimeseriesResponse(granularity=granularity, points=points)

    # Hour granularity: re-bucket in Python for SQLite/Postgres portability
    # (no shared date-truncation function across both dialects).
    hourly: dict[datetime, dict[str, int]] = defaultdict(lambda: {"total": 0, "blocked": 0, "allowed": 0})
    for row in rows:
        hour_bucket = row.bucket_ts.replace(minute=0, second=0, microsecond=0)
        hourly[hour_bucket]["total"] += row.total_requests
        hourly[hour_bucket]["blocked"] += row.blocked_requests
        hourly[hour_bucket]["allowed"] += row.allowed_requests

    points = [
        TimeseriesPoint(
            bucket_ts=bucket,
            total_requests=totals["total"],
            blocked_requests=totals["blocked"],
            allowed_requests=totals["allowed"],
        )
        for bucket, totals in sorted(hourly.items())
    ]
    return TimeseriesResponse(granularity=granularity, points=points)


async def _domains_in_category(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    category: DomainCategoryLabel,
    overrides: dict[str, DomainCategoryLabel],
) -> set[str]:
    domains = (
        await session.execute(
            select(DomainMinuteAggregate.domain)
            .where(DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until)
            .distinct()
        )
    ).scalars().all()
    return {domain for domain in domains if effective_category(domain, overrides) == category}


async def get_top_domains(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    limit: int,
    blocked_only: bool = False,
    order_by: Literal["requests", "blocked", "bytes"] | None = None,
    category: DomainCategoryLabel | None = None,
) -> list[DomainStat]:
    """`order_by` defaults to "blocked" when `blocked_only` is set (matching
    /api/top-blocked's intent) and "requests" otherwise, but can be
    overridden independently -- e.g. /api/top-data-usage wants every domain
    ordered by bytes without the blocked-only filter.

    `category` (admin override, falling back to the auto-inferred guess --
    see category_inference.effective_category) is resolved in a separate pass rather than in
    this query's SQL, since which category a domain falls under is Python
    business logic (category_inference.py), not something expressible as a
    join/case in a way that stays portable across SQLite and Postgres."""
    request_total = func.sum(DomainMinuteAggregate.request_count)
    blocked_total = func.sum(DomainMinuteAggregate.blocked_count)
    bytes_total = func.sum(DomainMinuteAggregate.total_bytes)

    effective_order_by = order_by or ("blocked" if blocked_only else "requests")
    order_columns = {"requests": request_total, "blocked": blocked_total, "bytes": bytes_total}
    order_col = order_columns[effective_order_by]

    overrides = await get_overrides_map(session)

    conditions = [DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until]
    if category is not None:
        matching_domains = await _domains_in_category(session, since, until, category, overrides)
        if not matching_domains:
            return []
        conditions.append(DomainMinuteAggregate.domain.in_(matching_domains))

    query = (
        select(DomainMinuteAggregate.domain, request_total, blocked_total, bytes_total)
        .where(*conditions)
        .group_by(DomainMinuteAggregate.domain)
    )
    if blocked_only:
        query = query.having(blocked_total > 0)
    query = query.order_by(order_col.desc()).limit(limit)

    rows = (await session.execute(query)).all()
    return [
        DomainStat(
            domain=domain,
            request_count=req_count,
            blocked_count=blocked_count,
            total_bytes=size,
            category=effective_category(domain, overrides),
        )
        for domain, req_count, blocked_count, size in rows
    ]


async def get_usage_by_category(
    session: AsyncSession, since: datetime, until: datetime
) -> list[CategoryStat]:
    """Every domain in `domain_minute_aggregates` gets bucketed under its
    effective category (admin override, else the auto-inferred guess --
    see category_inference.effective_category) rather than a flat "uncategorized", so a fresh
    deployment with no admin-assigned categories yet still shows a useful
    breakdown instead of one giant uncategorized bucket."""
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.request_count),
                func.sum(DomainMinuteAggregate.blocked_count),
                func.sum(DomainMinuteAggregate.total_bytes),
            )
            .where(DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until)
            .group_by(DomainMinuteAggregate.domain)
        )
    ).all()

    overrides = await get_overrides_map(session)
    totals: dict[DomainCategoryLabel, dict[str, int]] = defaultdict(
        lambda: {"requests": 0, "blocked": 0, "bytes": 0}
    )
    for domain, requests, blocked, size in rows:
        category = effective_category(domain, overrides)
        totals[category]["requests"] += requests
        totals[category]["blocked"] += blocked
        totals[category]["bytes"] += size

    items = [
        CategoryStat(
            category=category,
            request_count=totals_for["requests"],
            blocked_count=totals_for["blocked"],
            total_bytes=totals_for["bytes"],
        )
        for category, totals_for in totals.items()
    ]
    items.sort(key=lambda item: item.total_bytes, reverse=True)
    return items
