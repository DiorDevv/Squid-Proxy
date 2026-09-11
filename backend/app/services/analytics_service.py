"""Read-side aggregation for the Analytics section.

Like `report_service.py`, this reuses the queries the dashboard already
runs (`stats_service`) and adds a few cross-cutting rollups on top --
period-over-period comparison, per-branch breakdown, per-branch attention
signals, and an hour x weekday activity heatmap. Nothing here writes,
and there is no analytics-specific table: every number comes from
`minute_aggregates`, `domain_minute_aggregates`, `anomaly_events` and
`alert_settings`.

All timestamps are UTC (that is how buckets are stored), including the
weekday/hour split in the heatmap.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_BRANCH, get_settings
from app.models.alert_settings import AlertSettings
from app.models.anomaly_event import AnomalyEvent
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.schemas.analytics import (
    ActivityHeatmapResponse,
    AnalyticsOverview,
    BranchBlockedDomainRow,
    BranchBlockedDomainsResponse,
    BranchBlockedDomainsSeries,
    BranchBreakdownResponse,
    BranchBreakdownRow,
    BranchCategoryBreakdownResponse,
    BranchCategoryBreakdownSeries,
    BranchCategoryUsage,
    BranchSignalRow,
    BranchSignalsResponse,
    BranchTrendPoint,
    BranchTrendResponse,
    BranchTrendSeries,
    CategoryMover,
    CategoryTrendPoint,
    CategoryTrendResponse,
    CategoryUsage,
    DomainUsage,
    HeatmapCell,
    MetricDelta,
    TrendGranularity,
    TrendMetric,
)
from app.schemas.domains import DomainStat
from app.services import alert_settings_service, stats_service
from app.services.category_inference import effective_category
from app.services.client_service import client_bucket_rows
from app.services.domain_category_service import get_overrides_map

_QUOTA_ANOMALY_KIND = "client_quota_exceeded"


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


def _branches_in_scope(branch: str | None) -> list[str]:
    """A branch-scoped caller only ever sees their own branch; an
    unrestricted caller sees every configured branch (even one with no
    traffic in the window -- "which branch went quiet" is a useful thing to
    see)."""
    if branch is not None:
        return [branch]
    sources = get_settings().effective_log_sources
    seen: dict[str, None] = {}
    for source in sources:
        seen.setdefault(source.branch, None)
    return list(seen) or [DEFAULT_BRANCH]


async def _minute_totals(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> tuple[int, int, int, int]:
    """(total_requests, blocked_requests, allowed_requests, total_bytes) for
    one window, summed across the branch filter."""
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(MinuteAggregate.total_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.blocked_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.allowed_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.total_bytes), 0),
            ).where(*conditions)
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


async def _active_client_count(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> int:
    combined = client_bucket_rows(since, until, branch=branch)
    return int((await session.execute(select(func.count(func.distinct(combined.c.client_ip))))).scalar_one())


async def get_overview(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> AnalyticsOverview:
    duration = until - since
    prev_until = since
    prev_since = since - duration

    cur_req, cur_blocked, cur_allowed, cur_bytes = await _minute_totals(session, since, until, branch)
    prev_req, prev_blocked, prev_allowed, prev_bytes = await _minute_totals(
        session, prev_since, prev_until, branch
    )
    cur_clients = await _active_client_count(session, since, until, branch)
    prev_clients = await _active_client_count(session, prev_since, prev_until, branch)

    cur_cache = await stats_service.get_cache_efficiency(session, since, until, branch)
    prev_cache = await stats_service.get_cache_efficiency(session, prev_since, prev_until, branch)

    cur_ratio = (cur_blocked / cur_req) if cur_req else 0.0
    prev_ratio = (prev_blocked / prev_req) if prev_req else None

    def delta(metric: str, current: float, previous: float | None) -> MetricDelta:
        return MetricDelta(
            metric=metric,
            current=current,
            previous=previous,
            pct_change=_pct_change(current, previous),
        )

    metrics = [
        delta("total_requests", cur_req, prev_req),
        delta("blocked_requests", cur_blocked, prev_blocked),
        delta("allowed_requests", cur_allowed, prev_allowed),
        delta("total_bytes", cur_bytes, prev_bytes),
        delta("active_clients", cur_clients, prev_clients),
        delta("blocked_ratio", cur_ratio, prev_ratio),
        delta(
            "cache_hit_ratio",
            cur_cache.hit_ratio if cur_cache.hit_ratio is not None else 0.0,
            prev_cache.hit_ratio,
        ),
    ]

    by_category = await stats_service.get_usage_by_category(session, since, until, branch)
    top_categories = [
        CategoryUsage(
            category=item.category,
            request_count=item.request_count,
            blocked_count=item.blocked_count,
            total_bytes=item.total_bytes,
        )
        for item in by_category[:8]
    ]

    prev_by_category = await stats_service.get_usage_by_category(session, prev_since, prev_until, branch)
    cur_cat_bytes = {c.category: c.total_bytes for c in by_category}
    prev_cat_bytes = {c.category: c.total_bytes for c in prev_by_category}
    movers = [
        CategoryMover(
            category=category,
            current_bytes=cur_cat_bytes.get(category, 0),
            previous_bytes=prev_cat_bytes.get(category, 0),
            pct_change=_pct_change(cur_cat_bytes.get(category, 0), prev_cat_bytes.get(category) or None),
        )
        for category in cur_cat_bytes.keys() | prev_cat_bytes.keys()
    ]
    movers.sort(key=lambda m: abs(m.current_bytes - m.previous_bytes), reverse=True)
    top_movers = movers[:6]

    top_domains_raw = await stats_service.get_top_domains(
        session, since, until, limit=8, blocked_only=False, order_by="requests", branch=branch
    )
    top_blocked_raw = await stats_service.get_top_domains(
        session, since, until, limit=8, blocked_only=True, order_by="blocked", branch=branch
    )

    def to_domain_usage(item: DomainStat) -> DomainUsage:
        return DomainUsage(
            domain=item.domain,
            request_count=item.request_count,
            blocked_count=item.blocked_count,
            total_bytes=item.total_bytes,
            category=item.category,
        )

    return AnalyticsOverview(
        since=since,
        until=until,
        previous_since=prev_since,
        previous_until=prev_until,
        metrics=metrics,
        blocked_ratio=cur_ratio,
        cache_hit_ratio=cur_cache.hit_ratio,
        top_categories=top_categories,
        top_domains=[to_domain_usage(item) for item in top_domains_raw],
        top_blocked_domains=[to_domain_usage(item) for item in top_blocked_raw],
        top_movers=top_movers,
    )


def _truncate(ts: datetime, granularity: TrendGranularity) -> datetime:
    if granularity == TrendGranularity.DAY:
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return ts.replace(minute=0, second=0, microsecond=0)


def _drop_in_progress_bucket(keys: list[datetime], granularity: TrendGranularity) -> set[datetime]:
    """The bucket covering "now" is still filling, so plotting it makes every
    live time series look like it just dropped. Returns the bucket key(s) to
    exclude -- only ever the current one, and only when the series actually
    reaches the present (a historical range has no such bucket, so nothing
    is dropped)."""
    current = _truncate(datetime.now(UTC), granularity)
    return {k for k in keys if k >= current}


async def get_category_trend(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: TrendGranularity,
    metric: TrendMetric,
    branch: str | None,
) -> CategoryTrendResponse:
    # Coarsen an hourly request to daily once the window is wide enough that
    # hourly would blow past CATEGORY_TREND_MAX_BUCKETS points -- the
    # response reports the granularity actually used, so the client renders
    # the axis correctly instead of assuming it got what it asked for.
    effective_granularity = granularity
    if granularity == TrendGranularity.HOUR:
        hours = (until - since).total_seconds() / 3600
        if hours > get_settings().CATEGORY_TREND_MAX_BUCKETS:
            effective_granularity = TrendGranularity.DAY

    conditions = [
        DomainMinuteAggregate.bucket_ts >= since,
        DomainMinuteAggregate.bucket_ts <= until,
    ]
    if branch is not None:
        conditions.append(DomainMinuteAggregate.branch == branch)

    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.bucket_ts,
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.request_count),
                func.sum(DomainMinuteAggregate.total_bytes),
            )
            .where(*conditions)
            .group_by(DomainMinuteAggregate.bucket_ts, DomainMinuteAggregate.domain)
        )
    ).all()

    overrides = await get_overrides_map(session)

    # bucket -> category value -> summed metric
    buckets: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)
    for bucket_ts, domain, req_count, total_bytes in rows:
        category = effective_category(domain, overrides)
        value = int(total_bytes if metric == TrendMetric.BYTES else req_count)
        if value <= 0:
            continue
        key = _truncate(bucket_ts, effective_granularity)
        buckets[key][category.value] += value
        totals[category.value] += value

    ordered_categories = [
        DomainCategoryLabel(name) for name, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    drop = _drop_in_progress_bucket(list(buckets), effective_granularity)
    points = [
        CategoryTrendPoint(bucket_ts=bucket, values=dict(values))
        for bucket, values in sorted(buckets.items())
        if bucket not in drop
    ]
    return CategoryTrendResponse(
        granularity=effective_granularity, metric=metric, categories=ordered_categories, points=points
    )


async def _branch_minute_totals(
    session: AsyncSession, since: datetime, until: datetime, branches: list[str]
) -> dict[str, tuple[int, int, int, int]]:
    rows = (
        await session.execute(
            select(
                MinuteAggregate.branch,
                func.coalesce(func.sum(MinuteAggregate.total_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.blocked_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.allowed_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.total_bytes), 0),
            )
            .where(
                MinuteAggregate.bucket_ts >= since,
                MinuteAggregate.bucket_ts <= until,
                MinuteAggregate.branch.in_(branches),
            )
            .group_by(MinuteAggregate.branch)
        )
    ).all()
    result: dict[str, tuple[int, int, int, int]] = {b: (0, 0, 0, 0) for b in branches}
    for branch, total, blocked, allowed, total_bytes in rows:
        result[branch] = (int(total), int(blocked), int(allowed), int(total_bytes))
    return result


async def _branch_active_clients(
    session: AsyncSession, since: datetime, until: datetime, branches: list[str]
) -> dict[str, int]:
    combined = client_bucket_rows(since, until)
    rows = (
        await session.execute(
            select(combined.c.branch, func.count(func.distinct(combined.c.client_ip)))
            .where(combined.c.branch.in_(branches))
            .group_by(combined.c.branch)
        )
    ).all()
    result: dict[str, int] = {b: 0 for b in branches}
    for branch, count in rows:
        result[branch] = int(count)
    return result


async def get_branch_breakdown(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> BranchBreakdownResponse:
    branches = _branches_in_scope(branch)
    duration = until - since
    current = await _branch_minute_totals(session, since, until, branches)
    previous = await _branch_minute_totals(session, since - duration, since, branches)
    clients = await _branch_active_clients(session, since, until, branches)

    rows: list[BranchBreakdownRow] = []
    for b in branches:
        total, blocked, allowed, total_bytes = current[b]
        prev_total = previous[b][0]
        rows.append(
            BranchBreakdownRow(
                branch=b,
                total_requests=total,
                blocked_requests=blocked,
                allowed_requests=allowed,
                total_bytes=total_bytes,
                blocked_ratio=(blocked / total) if total else 0.0,
                active_client_count=clients[b],
                requests_pct_change=_pct_change(total, prev_total or None),
            )
        )
    rows.sort(key=lambda r: r.total_requests, reverse=True)
    return BranchBreakdownResponse(rows=rows)


async def get_branch_trend(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: TrendGranularity,
    branch: str | None,
) -> BranchTrendResponse:
    """Requests-over-time, split by branch -- the small-multiples view on
    the Branches tab. Same auto-coarsening and in-progress-bucket drop as
    get_category_trend, applied per branch so a quiet branch doesn't get a
    misleadingly flat line just because a busy one pushed the range wider."""
    effective_granularity = granularity
    if granularity == TrendGranularity.HOUR:
        hours = (until - since).total_seconds() / 3600
        if hours > get_settings().CATEGORY_TREND_MAX_BUCKETS:
            effective_granularity = TrendGranularity.DAY

    branches = _branches_in_scope(branch)
    rows = (
        await session.execute(
            select(
                MinuteAggregate.branch,
                MinuteAggregate.bucket_ts,
                func.sum(MinuteAggregate.total_requests),
                func.sum(MinuteAggregate.blocked_requests),
                func.sum(MinuteAggregate.allowed_requests),
                func.sum(MinuteAggregate.total_bytes),
            )
            .where(
                MinuteAggregate.bucket_ts >= since,
                MinuteAggregate.bucket_ts <= until,
                MinuteAggregate.branch.in_(branches),
            )
            .group_by(MinuteAggregate.branch, MinuteAggregate.bucket_ts)
        )
    ).all()

    # branch -> truncated bucket -> [requests, blocked, allowed, bytes]
    buckets: dict[str, dict[datetime, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for branch_name, bucket_ts, total_requests, blocked_requests, allowed_requests, total_bytes in rows:
        cell = buckets[branch_name][_truncate(bucket_ts, effective_granularity)]
        cell[0] += int(total_requests)
        cell[1] += int(blocked_requests)
        cell[2] += int(allowed_requests)
        cell[3] += int(total_bytes)

    series: list[BranchTrendSeries] = []
    for b in branches:
        branch_buckets = buckets.get(b, {})
        drop = _drop_in_progress_bucket(list(branch_buckets), effective_granularity)
        points = [
            BranchTrendPoint(
                bucket_ts=bucket,
                total_requests=vals[0],
                blocked_requests=vals[1],
                allowed_requests=vals[2],
                total_bytes=vals[3],
            )
            for bucket, vals in sorted(branch_buckets.items())
            if bucket not in drop
        ]
        series.append(BranchTrendSeries(branch=b, points=points))

    return BranchTrendResponse(granularity=effective_granularity, series=series)


async def get_branch_category_breakdown(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> BranchCategoryBreakdownResponse:
    """What each branch's traffic is actually going to, by category -- one
    query over domain_minute_aggregates grouped by (branch, domain), each
    domain resolved to its effective category and summed in Python (same
    shape as _branch_category_bytes, plus request_count so the frontend can
    show share-of-requests as well as share-of-bytes)."""
    branches = _branches_in_scope(branch)
    overrides = await get_overrides_map(session)
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.branch,
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.request_count),
                func.sum(DomainMinuteAggregate.total_bytes),
            )
            .where(
                DomainMinuteAggregate.bucket_ts >= since,
                DomainMinuteAggregate.bucket_ts <= until,
                DomainMinuteAggregate.branch.in_(branches),
            )
            .group_by(DomainMinuteAggregate.branch, DomainMinuteAggregate.domain)
        )
    ).all()

    # branch -> category -> [requests, bytes]
    totals: dict[str, dict[DomainCategoryLabel, list[int]]] = {
        b: defaultdict(lambda: [0, 0]) for b in branches
    }
    for branch_name, domain, request_count, total_bytes in rows:
        cell = totals[branch_name][effective_category(domain, overrides)]
        cell[0] += int(request_count)
        cell[1] += int(total_bytes)

    series = [
        BranchCategoryBreakdownSeries(
            branch=b,
            categories=sorted(
                (
                    BranchCategoryUsage(category=category, request_count=vals[0], total_bytes=vals[1])
                    for category, vals in totals[b].items()
                ),
                key=lambda c: c.total_bytes,
                reverse=True,
            ),
        )
        for b in branches
    ]
    return BranchCategoryBreakdownResponse(series=series)


async def get_branch_top_blocked_domains(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None, limit: int = 8
) -> BranchBlockedDomainsResponse:
    """Which domains a branch is blocking the most -- one query grouped by
    (branch, domain) across every branch in scope, top-N sliced per branch
    in Python so a heavily-blocked branch can't crowd a quieter branch's own
    list out of the response."""
    branches = _branches_in_scope(branch)
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.branch,
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.blocked_count),
            )
            .where(
                DomainMinuteAggregate.bucket_ts >= since,
                DomainMinuteAggregate.bucket_ts <= until,
                DomainMinuteAggregate.branch.in_(branches),
            )
            .group_by(DomainMinuteAggregate.branch, DomainMinuteAggregate.domain)
            .having(func.sum(DomainMinuteAggregate.blocked_count) > 0)
        )
    ).all()

    by_branch: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for branch_name, domain, blocked_count in rows:
        by_branch[branch_name].append((domain, int(blocked_count)))

    series = [
        BranchBlockedDomainsSeries(
            branch=b,
            domains=[
                BranchBlockedDomainRow(domain=domain, blocked_count=count)
                for domain, count in sorted(by_branch.get(b, []), key=lambda x: x[1], reverse=True)[:limit]
            ],
        )
        for b in branches
    ]
    return BranchBlockedDomainsResponse(since=since, until=until, series=series)


async def _branch_alert_inputs(
    session: AsyncSession, branches: list[str]
) -> tuple[dict[str, set[DomainCategoryLabel]], dict[str, int | None]]:
    """Per-branch (sensitive category set, uncategorized-domain request
    threshold) in one query. A branch with no persisted AlertSettings row
    yet falls back to the same defaults alert_settings_service would return
    for it (no sensitive categories, no threshold) without a second query.
    """
    existing = {
        row.branch: row
        for row in (
            await session.execute(select(AlertSettings).where(AlertSettings.branch.in_(branches)))
        ).scalars()
    }
    sensitive: dict[str, set[DomainCategoryLabel]] = {}
    thresholds: dict[str, int | None] = {}
    for branch in branches:
        row = existing.get(branch)
        sensitive[branch] = alert_settings_service.parse_sensitive_categories(
            row.sensitive_categories if row else ""
        )
        thresholds[branch] = row.uncategorized_domain_request_threshold if row else None
    return sensitive, thresholds


async def _branch_category_bytes(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branches: list[str],
    overrides: dict[str, DomainCategoryLabel],
) -> dict[str, dict[DomainCategoryLabel, int]]:
    """Per-branch bytes-per-effective-category, one query over
    domain_minute_aggregates grouped by (branch, domain)."""
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.branch,
                DomainMinuteAggregate.domain,
                func.coalesce(func.sum(DomainMinuteAggregate.total_bytes), 0),
            )
            .where(
                DomainMinuteAggregate.bucket_ts >= since,
                DomainMinuteAggregate.bucket_ts <= until,
                DomainMinuteAggregate.branch.in_(branches),
            )
            .group_by(DomainMinuteAggregate.branch, DomainMinuteAggregate.domain)
        )
    ).all()
    result: dict[str, dict[DomainCategoryLabel, int]] = {b: defaultdict(int) for b in branches}
    for branch, domain, total_bytes in rows:
        result[branch][effective_category(domain, overrides)] += int(total_bytes)
    return result


async def _branch_anomaly_stats(
    session: AsyncSession, since: datetime, until: datetime, branches: list[str]
) -> dict[str, tuple[int, int]]:
    """Per-branch (total anomaly count, quota-breach count) in one query
    grouped by (branch, kind)."""
    rows = (
        await session.execute(
            select(AnomalyEvent.branch, AnomalyEvent.kind, func.count())
            .where(
                AnomalyEvent.generated_at >= since,
                AnomalyEvent.generated_at <= until,
                AnomalyEvent.branch.in_(branches),
            )
            .group_by(AnomalyEvent.branch, AnomalyEvent.kind)
        )
    ).all()
    counts: dict[str, int] = {b: 0 for b in branches}
    quota: dict[str, int] = {b: 0 for b in branches}
    for branch, kind, n in rows:
        count = int(n)
        counts[branch] += count
        if kind == _QUOTA_ANOMALY_KIND:
            quota[branch] += count
    return {b: (counts[b], quota[b]) for b in branches}


async def _branch_uncategorized_counts(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branches: list[str],
    thresholds: dict[str, int | None],
    overrides: dict[str, DomainCategoryLabel],
) -> dict[str, int]:
    """Per-branch count of domains whose range request total meets that
    branch's uncategorized-domain threshold *and* which still resolve to
    the 'uncategorized' category, one query grouped by (branch, domain)."""
    active = [b for b in branches if thresholds.get(b)]
    result: dict[str, int] = {b: 0 for b in branches}
    if not active:
        return result
    rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.branch,
                DomainMinuteAggregate.domain,
                func.coalesce(func.sum(DomainMinuteAggregate.request_count), 0),
            )
            .where(
                DomainMinuteAggregate.bucket_ts >= since,
                DomainMinuteAggregate.bucket_ts <= until,
                DomainMinuteAggregate.branch.in_(active),
            )
            .group_by(DomainMinuteAggregate.branch, DomainMinuteAggregate.domain)
        )
    ).all()
    for branch, domain, request_count in rows:
        threshold = thresholds.get(branch)
        if not threshold or int(request_count) < threshold:
            continue
        if effective_category(domain, overrides) == DomainCategoryLabel.UNCATEGORIZED:
            result[branch] += 1
    return result


async def get_branch_signals(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> BranchSignalsResponse:
    """The raw per-branch attention signals -- blocked ratio, sensitive
    traffic share, anomaly count, quota breaches, uncategorized-domain count
    -- side by side, with no composite score or band. Runs a fixed handful
    of grouped queries regardless of branch count, not a per-branch loop.
    Sorted by blocked ratio then anomaly count so the branch most likely to
    need a look is first; the frontend table is re-sortable by any column."""
    branches = _branches_in_scope(branch)

    totals = await _branch_minute_totals(session, since, until, branches)
    overrides = await get_overrides_map(session)
    sensitive_by_branch, thresholds = await _branch_alert_inputs(session, branches)
    category_bytes = await _branch_category_bytes(session, since, until, branches, overrides)
    anomaly_stats = await _branch_anomaly_stats(session, since, until, branches)
    uncategorized = await _branch_uncategorized_counts(session, since, until, branches, thresholds, overrides)

    rows: list[BranchSignalRow] = []
    for b in branches:
        total, blocked, _allowed, _total_bytes = totals[b]
        blocked_ratio = (blocked / total) if total else 0.0

        sensitive = sensitive_by_branch[b]
        sensitive_share = 0.0
        if sensitive:
            # Share of *domain-attributed* bytes, not of MinuteAggregate's
            # total_bytes -- the latter also counts CONNECT tunnels and
            # other traffic with no domain, which would silently deflate the
            # ratio on an HTTPS-heavy deployment.
            categorized_bytes = sum(category_bytes[b].values())
            if categorized_bytes:
                sensitive_bytes = sum(v for cat, v in category_bytes[b].items() if cat in sensitive)
                sensitive_share = sensitive_bytes / categorized_bytes

        anomaly_count, quota_breaches = anomaly_stats[b]

        rows.append(
            BranchSignalRow(
                branch=b,
                total_requests=total,
                blocked_requests=blocked,
                blocked_ratio=round(blocked_ratio, 4),
                sensitive_traffic_share=round(sensitive_share, 4),
                anomaly_count=anomaly_count,
                quota_breach_count=quota_breaches,
                uncategorized_domain_count=uncategorized[b],
            )
        )
    rows.sort(key=lambda r: (r.blocked_ratio, r.anomaly_count), reverse=True)
    return BranchSignalsResponse(since=since, until=until, rows=rows)


async def get_activity_heatmap(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: str | None,
    blocked_only: bool,
    tz_offset_minutes: int = 0,
) -> ActivityHeatmapResponse:
    """Weekday x hour grid of request volume. `tz_offset_minutes` (minutes
    east of UTC, e.g. 300 for UTC+5) shifts the stored-UTC bucket
    timestamps before the weekday/hour split so the grid reads in the
    viewer's local time; 0 keeps it in UTC."""
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)

    rows = (
        await session.execute(
            select(
                MinuteAggregate.bucket_ts,
                func.sum(MinuteAggregate.total_requests),
                func.sum(MinuteAggregate.blocked_requests),
            )
            .where(*conditions)
            .group_by(MinuteAggregate.bucket_ts)
        )
    ).all()

    shift = timedelta(minutes=tz_offset_minutes)
    grid: dict[tuple[int, int], int] = defaultdict(int)
    for bucket_ts, total, blocked in rows:
        value = int(blocked if blocked_only else total)
        if value <= 0:
            continue
        local = bucket_ts + shift
        grid[(local.weekday(), local.hour)] += value

    cells = [HeatmapCell(weekday=wd, hour=hr, value=value) for (wd, hr), value in sorted(grid.items())]
    max_value = max((c.value for c in cells), default=0)
    return ActivityHeatmapResponse(
        blocked_only=blocked_only,
        tz_offset_minutes=tz_offset_minutes,
        max_value=max_value,
        cells=cells,
    )
