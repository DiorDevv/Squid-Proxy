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
from app.schemas.summary import CacheEfficiencyResponse, SummaryResponse
from app.schemas.timeseries import TimeseriesPoint, TimeseriesResponse
from app.services.category_inference import effective_category
from app.services.client_service import client_bucket_rows
from app.services.domain_category_service import get_overrides_map


async def get_summary(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    range_param: RangeParam | None,
    branch: str | None = None,
) -> SummaryResponse:
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)
    totals_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(MinuteAggregate.total_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.blocked_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.allowed_requests), 0),
            ).where(*conditions)
        )
    ).one()
    total_requests, blocked_requests, allowed_requests = totals_row

    # Reads client_minute_aggregates and client_hourly_aggregates combined
    # (see client_bucket_rows) -- a range extending past the rollup cutoff
    # (retention.py) would otherwise silently undercount, since older
    # activity has been compressed into the hourly table and the source
    # minute rows deleted.
    combined = client_bucket_rows(since, until, branch=branch)

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


async def get_cache_efficiency(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None = None
) -> CacheEfficiencyResponse:
    """How much of this window's traffic Squid served from cache vs. fetched
    fresh -- see MinuteAggregate.hit_requests/miss_requests and
    aggregator._is_cache_hit/_is_cache_miss for how each request is
    classified. Reads MinuteAggregate directly (not client_bucket_rows'
    minute+hourly union): unlike per-client aggregates, this table is never
    rolled up into an hourly table (see retention.py), so it's already at
    minute granularity for its whole retention window."""
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)

    hit_requests, miss_requests = (
        await session.execute(
            select(
                func.coalesce(func.sum(MinuteAggregate.hit_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.miss_requests), 0),
            ).where(*conditions)
        )
    ).one()

    cacheable = hit_requests + miss_requests
    hit_ratio = (hit_requests / cacheable) if cacheable > 0 else None
    return CacheEfficiencyResponse(
        hit_requests=hit_requests, miss_requests=miss_requests, hit_ratio=hit_ratio
    )


async def get_timeseries(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: Granularity,
    branch: str | None = None,
) -> TimeseriesResponse:
    # Grouped by bucket_ts (summing across branches) rather than selecting
    # MinuteAggregate rows directly: that table is now unique per
    # (bucket_ts, branch), so a `branch=None` ("all branches") request can
    # have more than one row per minute, and returning them ungrouped would
    # produce duplicate/incorrect points instead of one combined total per
    # minute. When `branch` is given this is equivalent to the old
    # row-per-minute behavior, just expressed the same way for both cases.
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)
    rows = (
        await session.execute(
            select(
                MinuteAggregate.bucket_ts,
                func.sum(MinuteAggregate.total_requests),
                func.sum(MinuteAggregate.blocked_requests),
                func.sum(MinuteAggregate.allowed_requests),
            )
            .where(*conditions)
            .group_by(MinuteAggregate.bucket_ts)
            .order_by(MinuteAggregate.bucket_ts)
        )
    ).all()

    if granularity == Granularity.MINUTE:
        points = [
            TimeseriesPoint(
                bucket_ts=bucket_ts,
                total_requests=total_requests,
                blocked_requests=blocked_requests,
                allowed_requests=allowed_requests,
            )
            for bucket_ts, total_requests, blocked_requests, allowed_requests in rows
        ]
        return TimeseriesResponse(granularity=granularity, points=points)

    # Hour granularity: re-bucket in Python for SQLite/Postgres portability
    # (no shared date-truncation function across both dialects).
    hourly: dict[datetime, dict[str, int]] = defaultdict(lambda: {"total": 0, "blocked": 0, "allowed": 0})
    for bucket_ts, total_requests, blocked_requests, allowed_requests in rows:
        hour_bucket = bucket_ts.replace(minute=0, second=0, microsecond=0)
        hourly[hour_bucket]["total"] += total_requests
        hourly[hour_bucket]["blocked"] += blocked_requests
        hourly[hour_bucket]["allowed"] += allowed_requests

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
    branch: str | None = None,
) -> set[str]:
    conditions = [DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(DomainMinuteAggregate.branch == branch)
    domains = (
        await session.execute(select(DomainMinuteAggregate.domain).where(*conditions).distinct())
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
    branch: str | None = None,
    search: str | None = None,
) -> list[DomainStat]:
    """`order_by` defaults to "blocked" when `blocked_only` is set (matching
    /api/top-blocked's intent) and "requests" otherwise, but can be
    overridden independently -- e.g. /api/top-data-usage wants every domain
    ordered by bytes without the blocked-only filter.

    `category` (admin override, falling back to the auto-inferred guess --
    see category_inference.effective_category) is resolved in a separate pass rather than in
    this query's SQL, since which category a domain falls under is Python
    business logic (category_inference.py), not something expressible as a
    join/case in a way that stays portable across SQLite and Postgres.

    `search`, when given, filters to domains containing it (case-insensitive
    substring, same convention as client_service.list_clients) -- used by
    /api/domains/search for the global search box."""
    request_total = func.sum(DomainMinuteAggregate.request_count)
    blocked_total = func.sum(DomainMinuteAggregate.blocked_count)
    bytes_total = func.sum(DomainMinuteAggregate.total_bytes)

    effective_order_by = order_by or ("blocked" if blocked_only else "requests")
    order_columns = {"requests": request_total, "blocked": blocked_total, "bytes": bytes_total}
    order_col = order_columns[effective_order_by]

    overrides = await get_overrides_map(session)

    conditions = [DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(DomainMinuteAggregate.branch == branch)
    if category is not None:
        matching_domains = await _domains_in_category(session, since, until, category, overrides, branch)
        if not matching_domains:
            return []
        conditions.append(DomainMinuteAggregate.domain.in_(matching_domains))
    if search and search.strip():
        conditions.append(DomainMinuteAggregate.domain.ilike(f"%{search.strip()}%"))

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
    session: AsyncSession, since: datetime, until: datetime, branch: str | None = None
) -> list[CategoryStat]:
    """Every domain in `domain_minute_aggregates` gets bucketed under its
    effective category (admin override, else the auto-inferred guess --
    see category_inference.effective_category) rather than a flat "uncategorized", so a fresh
    deployment with no admin-assigned categories yet still shows a useful
    breakdown instead of one giant uncategorized bucket."""
    conditions = [DomainMinuteAggregate.bucket_ts >= since, DomainMinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(DomainMinuteAggregate.branch == branch)
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.request_count),
                func.sum(DomainMinuteAggregate.blocked_count),
                func.sum(DomainMinuteAggregate.total_bytes),
            )
            .where(*conditions)
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
