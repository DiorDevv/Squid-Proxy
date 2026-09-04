"""Read-side queries behind the Analytics section's Squid-operational views.

"Traffic & cache" and "Blocks" run entirely off the per-minute aggregate
tables from migration f3b8d1c6a274 (result code, HTTP method/status,
hierarchy) plus the response-time histogram on minute_aggregates -- no
per-request scanning. "Who" runs off the client/user aggregates for the
leaderboard, and reads raw_events for exactly one selected actor's
drill-down detail.

All timestamps are UTC. Branch scoping mirrors api.deps.resolve_branch:
None = every branch, a concrete tag = just that one.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.models.ops_aggregate import (
    HierarchyMinuteAggregate,
    HttpMinuteAggregate,
    ResultCodeMinuteAggregate,
    UserCategoryMinuteAggregate,
)
from app.models.raw_event import RawEvent
from app.schemas.analytics import TrendGranularity
from app.schemas.squid_ops import (
    ActorCategorySlice,
    ActorDetailResponse,
    ActorDomainRow,
    ActorLeaderboardResponse,
    ActorRow,
    BranchIngestRow,
    DenialReasonPoint,
    DenialsResponse,
    HierarchyResponse,
    HttpBreakdownResponse,
    IngestHealthResponse,
    NamedCount,
    NewEntitiesResponse,
    ResponseTimePoint,
    ResponseTimeResponse,
    ResultCodeResponse,
    TimeBucketCounts,
)
from app.services.aggregator import _is_cache_hit, _is_cache_miss
from app.services.analytics_service import _drop_in_progress_bucket, _truncate
from app.services.category_inference import effective_category
from app.services.client_service import client_bucket_rows
from app.services.domain_category_service import get_overrides_map

_NEW_ENTITY_CAP = 50
_ACTOR_TOP_DOMAINS = 10

# (lower_ms, upper_ms | None, histogram column) in band order -- mirrors
# aggregator._add_duration.
_DUR_BANDS: list[tuple[int, int | None, str, str]] = [
    (0, 100, "dur_lt_100", "<100ms"),
    (100, 300, "dur_lt_300", "100-300ms"),
    (300, 1000, "dur_lt_1000", "300ms-1s"),
    (1000, 3000, "dur_lt_3000", "1-3s"),
    (3000, 10000, "dur_lt_10000", "3-10s"),
    (10000, None, "dur_gte_10000", ">=10s"),
]


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def _category_model_and_actor_col(is_user: bool) -> tuple[Any, Any]:
    """The right per-(actor, category) aggregate table + actor column: the
    user-keyed table when the deployment authenticates, else the IP-keyed
    one."""
    if is_user:
        return UserCategoryMinuteAggregate, UserCategoryMinuteAggregate.user
    return ClientCategoryMinuteAggregate, ClientCategoryMinuteAggregate.client_ip


def _percentile_from_hist(counts: list[int], p: float) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    target = math.ceil(p / 100 * total)
    cum = 0
    for (lo, hi, _col, _label), band_count in zip(_DUR_BANDS, counts, strict=True):
        if band_count == 0:
            continue
        if cum + band_count >= target:
            if hi is None:
                return float(lo)
            return round(lo + (hi - lo) * ((target - cum) / band_count), 1)
        cum += band_count
    return float(_DUR_BANDS[-1][0])


# --------------------------------------------------------------------------
# Traffic & cache
# --------------------------------------------------------------------------


async def get_result_codes(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: TrendGranularity,
    branch: str | None,
) -> ResultCodeResponse:
    conditions = [
        ResultCodeMinuteAggregate.bucket_ts >= since,
        ResultCodeMinuteAggregate.bucket_ts <= until,
    ]
    if branch is not None:
        conditions.append(ResultCodeMinuteAggregate.branch == branch)
    rows = (
        await session.execute(
            select(
                ResultCodeMinuteAggregate.bucket_ts,
                ResultCodeMinuteAggregate.action,
                func.sum(ResultCodeMinuteAggregate.request_count),
                func.sum(ResultCodeMinuteAggregate.total_bytes),
            )
            .where(*conditions)
            .group_by(ResultCodeMinuteAggregate.bucket_ts, ResultCodeMinuteAggregate.action)
        )
    ).all()

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # action -> [count, bytes]
    buckets: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hit_req = miss_req = denied_req = tunnel_req = grand_req = 0
    hit_bytes = miss_bytes = 0
    for bucket_ts, action, count, byte_total in rows:
        count = int(count)
        byte_total = int(byte_total)
        totals[action][0] += count
        totals[action][1] += byte_total
        buckets[_truncate(bucket_ts, granularity)][action] += count
        grand_req += count
        if _is_cache_hit(action):
            hit_req += count
            hit_bytes += byte_total
        elif _is_cache_miss(action):
            miss_req += count
            miss_bytes += byte_total
        upper = action.upper()
        if "DENIED" in upper:
            denied_req += count
        if "TUNNEL" in upper:
            tunnel_req += count

    codes = sorted(
        (
            NamedCount(
                label=action,
                request_count=cb[0],
                total_bytes=cb[1],
                pct=_pct(cb[0], grand_req),
            )
            for action, cb in totals.items()
        ),
        key=lambda c: c.request_count,
        reverse=True,
    )
    series_labels = [c.label for c in codes[:8]]
    drop = _drop_in_progress_bucket(list(buckets), granularity)
    series = [
        TimeBucketCounts(
            bucket_ts=bucket,
            values={label: values.get(label, 0) for label in series_labels},
        )
        for bucket, values in sorted(buckets.items())
        if bucket not in drop
    ]
    cacheable = hit_req + miss_req
    cacheable_bytes = hit_bytes + miss_bytes
    return ResultCodeResponse(
        granularity=granularity,
        hit_ratio=(hit_req / cacheable) if cacheable else None,
        byte_hit_ratio=(hit_bytes / cacheable_bytes) if cacheable_bytes else None,
        denied_ratio=(denied_req / grand_req) if grand_req else 0.0,
        tunnel_ratio=(tunnel_req / grand_req) if grand_req else 0.0,
        codes=codes,
        series_labels=series_labels,
        series=series,
    )


async def get_http_breakdown(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> HttpBreakdownResponse:
    conditions = [
        HttpMinuteAggregate.bucket_ts >= since,
        HttpMinuteAggregate.bucket_ts <= until,
    ]
    if branch is not None:
        conditions.append(HttpMinuteAggregate.branch == branch)
    rows = (
        await session.execute(
            select(
                HttpMinuteAggregate.method,
                HttpMinuteAggregate.status_code,
                func.sum(HttpMinuteAggregate.request_count),
                func.sum(HttpMinuteAggregate.total_bytes),
            )
            .where(*conditions)
            .group_by(HttpMinuteAggregate.method, HttpMinuteAggregate.status_code)
        )
    ).all()

    method_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    status_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    class_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    grand = 0
    denied_403 = proxy_auth_407 = server_error_5xx = 0
    for method, status_code, count, byte_total in rows:
        count = int(count)
        byte_total = int(byte_total)
        grand += count
        method_totals[method][0] += count
        method_totals[method][1] += byte_total
        status_label = str(status_code) if status_code else "-"
        status_totals[status_label][0] += count
        status_totals[status_label][1] += byte_total
        cls = f"{status_code // 100}xx" if status_code else "0"
        class_totals[cls][0] += count
        class_totals[cls][1] += byte_total
        if status_code == 403:
            denied_403 += count
        elif status_code == 407:
            proxy_auth_407 += count
        elif 500 <= status_code < 600:
            server_error_5xx += count

    def _named(items: dict[str, list[int]]) -> list[NamedCount]:
        return sorted(
            (
                NamedCount(
                    label=label,
                    request_count=v[0],
                    total_bytes=v[1],
                    pct=_pct(v[0], grand),
                )
                for label, v in items.items()
            ),
            key=lambda c: c.request_count,
            reverse=True,
        )

    return HttpBreakdownResponse(
        methods=_named(method_totals),
        status_codes=_named(status_totals),
        status_classes=_named(class_totals),
        denied_403=denied_403,
        proxy_auth_407=proxy_auth_407,
        server_error_5xx=server_error_5xx,
    )


async def get_hierarchy_breakdown(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> HierarchyResponse:
    conditions = [
        HierarchyMinuteAggregate.bucket_ts >= since,
        HierarchyMinuteAggregate.bucket_ts <= until,
    ]
    if branch is not None:
        conditions.append(HierarchyMinuteAggregate.branch == branch)
    rows = (
        await session.execute(
            select(
                HierarchyMinuteAggregate.hierarchy_code,
                func.sum(HierarchyMinuteAggregate.request_count),
                func.sum(HierarchyMinuteAggregate.total_bytes),
            )
            .where(*conditions)
            .group_by(HierarchyMinuteAggregate.hierarchy_code)
        )
    ).all()
    grand = sum(int(r[1]) for r in rows)
    codes = sorted(
        (
            NamedCount(
                label=code, request_count=int(count), total_bytes=int(byte_total), pct=_pct(int(count), grand)
            )
            for code, count, byte_total in rows
        ),
        key=lambda c: c.request_count,
        reverse=True,
    )
    return HierarchyResponse(codes=codes)


async def get_response_time(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: TrendGranularity,
    branch: str | None,
) -> ResponseTimeResponse:
    conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        conditions.append(MinuteAggregate.branch == branch)
    band_cols = [getattr(MinuteAggregate, col) for _lo, _hi, col, _label in _DUR_BANDS]
    rows = (
        await session.execute(
            select(
                MinuteAggregate.bucket_ts,
                func.sum(MinuteAggregate.duration_sum_ms),
                *[func.sum(col) for col in band_cols],
            )
            .where(*conditions)
            .group_by(MinuteAggregate.bucket_ts)
        )
    ).all()

    overall_bands = [0] * len(_DUR_BANDS)
    overall_sum = 0
    per_bucket: dict[datetime, tuple[int, list[int]]] = {}
    grouped: dict[datetime, list[int]] = defaultdict(lambda: [0] * (len(_DUR_BANDS) + 1))
    for row in rows:
        bucket_ts = row[0]
        dur_sum = int(row[1] or 0)
        bands = [int(v or 0) for v in row[2:]]
        key = _truncate(bucket_ts, granularity)
        acc = grouped[key]
        acc[0] += dur_sum
        for i, v in enumerate(bands):
            acc[i + 1] += v
        overall_sum += dur_sum
        for i, v in enumerate(bands):
            overall_bands[i] += v

    drop = _drop_in_progress_bucket(list(grouped), granularity)
    for key, acc in grouped.items():
        per_bucket[key] = (acc[0], acc[1:])

    series = [
        ResponseTimePoint(
            bucket_ts=key,
            p50=_percentile_from_hist(bands, 50),
            p95=_percentile_from_hist(bands, 95),
            p99=_percentile_from_hist(bands, 99),
            mean=round(dur_sum / sum(bands), 1) if sum(bands) else 0.0,
            request_count=sum(bands),
        )
        for key, (dur_sum, bands) in sorted(per_bucket.items())
        if key not in drop
    ]
    sample_count = sum(overall_bands)
    return ResponseTimeResponse(
        granularity=granularity,
        overall_p50=_percentile_from_hist(overall_bands, 50),
        overall_p95=_percentile_from_hist(overall_bands, 95),
        overall_p99=_percentile_from_hist(overall_bands, 99),
        overall_mean=round(overall_sum / sample_count, 1) if sample_count else 0.0,
        sample_count=sample_count,
        bands=[
            NamedCount(
                label=label,
                request_count=overall_bands[i],
                total_bytes=0,
                pct=_pct(overall_bands[i], sample_count),
            )
            for i, (_lo, _hi, _col, label) in enumerate(_DUR_BANDS)
        ],
        series=series,
    )


# --------------------------------------------------------------------------
# Who is doing what
# --------------------------------------------------------------------------

_SORTABLE = {
    "requests": "request_count",
    "bytes": "total_bytes",
    "blocked": "blocked_count",
}


async def _has_authenticated_users(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> bool:
    combined = client_bucket_rows(since, until, branch=branch)
    exists = (
        await session.execute(
            select(func.count())
            .select_from(combined)
            .where(combined.c.user.is_not(None), combined.c.user != "")
        )
    ).scalar_one()
    return int(exists) > 0


async def get_actor_leaderboard(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: str | None,
    limit: int,
    sort: str,
) -> ActorLeaderboardResponse:
    is_user = await _has_authenticated_users(session, since, until, branch)
    combined = client_bucket_rows(since, until, branch=branch)
    actor_col = combined.c.user if is_user else combined.c.client_ip
    order_col = {
        "request_count": func.sum(combined.c.request_count),
        "total_bytes": func.sum(combined.c.total_bytes),
        "blocked_count": func.sum(combined.c.blocked_count),
    }[_SORTABLE.get(sort, "request_count")]

    conditions: list[Any] = [actor_col.is_not(None)]
    if is_user:
        conditions.append(actor_col != "")
    rows = (
        await session.execute(
            select(
                actor_col,
                func.sum(combined.c.request_count),
                func.sum(combined.c.blocked_count),
                func.sum(combined.c.total_bytes),
            )
            .where(*conditions)
            .group_by(actor_col)
            .order_by(order_col.desc())
            .limit(limit)
        )
    ).all()
    actor_ids = [r[0] for r in rows]
    top_category = await _top_category_per_actor(session, since, until, branch, actor_ids, is_user)

    unattributed = 0
    if is_user:
        unattributed = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(combined.c.request_count), 0)).where(
                        (combined.c.user.is_(None)) | (combined.c.user == "")
                    )
                )
            ).scalar_one()
        )

    leaderboard = [
        ActorRow(
            actor=actor,
            is_user=is_user,
            request_count=int(req),
            blocked_count=int(blocked),
            blocked_ratio=(int(blocked) / int(req)) if req else 0.0,
            total_bytes=int(byte_total),
            top_category=top_category.get(actor),
        )
        for actor, req, blocked, byte_total in rows
    ]
    return ActorLeaderboardResponse(
        actor_kind="user" if is_user else "client_ip",
        rows=leaderboard,
        unattributed_requests=unattributed,
    )


async def _top_category_per_actor(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    branch: str | None,
    actor_ids: list[str],
    is_user: bool,
) -> dict[str, DomainCategoryLabel]:
    if not actor_ids:
        return {}
    model, actor_col = _category_model_and_actor_col(is_user)
    conditions: list[Any] = [
        model.bucket_ts >= since,
        model.bucket_ts <= until,
        actor_col.in_(actor_ids),
    ]
    if branch is not None:
        conditions.append(model.branch == branch)
    rows = (
        await session.execute(
            select(actor_col, model.category, func.sum(model.request_count))
            .where(*conditions)
            .group_by(actor_col, model.category)
        )
    ).all()
    best: dict[str, tuple[int, DomainCategoryLabel]] = {}
    for actor, category, count in rows:
        count = int(count)
        current = best.get(actor)
        if current is None or count > current[0]:
            best[actor] = (count, category)
    return {actor: category for actor, (_c, category) in best.items()}


async def get_actor_detail(
    session: AsyncSession,
    actor: str,
    is_user: bool,
    since: datetime,
    until: datetime,
    branch: str | None,
) -> ActorDetailResponse:
    combined = client_bucket_rows(since, until, branch=branch)
    actor_col = combined.c.user if is_user else combined.c.client_ip

    totals_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(combined.c.request_count), 0),
                func.coalesce(func.sum(combined.c.blocked_count), 0),
                func.coalesce(func.sum(combined.c.total_bytes), 0),
                func.min(combined.c.bucket_ts),
                func.max(combined.c.bucket_ts),
            ).where(actor_col == actor)
        )
    ).one()
    req_total, blocked_total, byte_total, first_seen, last_seen = totals_row

    # hourly (0-23, UTC)
    hourly_rows = (
        await session.execute(
            select(combined.c.bucket_ts, func.sum(combined.c.request_count))
            .where(actor_col == actor)
            .group_by(combined.c.bucket_ts)
        )
    ).all()
    hourly = [0] * 24
    for bucket_ts, count in hourly_rows:
        hourly[bucket_ts.hour] += int(count)

    # category split
    cat_model, cat_actor_col = _category_model_and_actor_col(is_user)
    cat_conditions: list[Any] = [
        cat_model.bucket_ts >= since,
        cat_model.bucket_ts <= until,
        cat_actor_col == actor,
    ]
    if branch is not None:
        cat_conditions.append(cat_model.branch == branch)
    cat_rows = (
        await session.execute(
            select(
                cat_model.category,
                func.sum(cat_model.request_count),
                func.sum(cat_model.total_bytes),
            )
            .where(*cat_conditions)
            .group_by(cat_model.category)
        )
    ).all()
    categories = sorted(
        (
            ActorCategorySlice(category=c, request_count=int(rc), total_bytes=int(tb))
            for c, rc, tb in cat_rows
        ),
        key=lambda s: s.total_bytes,
        reverse=True,
    )

    top_domains = await _actor_domains(session, actor, is_user, since, until, branch, blocked_only=False)
    denied_domains = await _actor_domains(
        session, actor, is_user, since, until, branch, blocked_only=True
    )

    return ActorDetailResponse(
        actor=actor,
        is_user=is_user,
        first_seen=first_seen,
        last_seen=last_seen,
        request_count=int(req_total),
        blocked_count=int(blocked_total),
        total_bytes=int(byte_total),
        categories=categories,
        top_domains=top_domains,
        denied_domains=denied_domains,
        hourly=hourly,
    )


async def _actor_domains(
    session: AsyncSession,
    actor: str,
    is_user: bool,
    since: datetime,
    until: datetime,
    branch: str | None,
    blocked_only: bool,
) -> list[ActorDomainRow]:
    """Top domains for one actor -- the one place "who" reaches into
    raw_events (indexed on client_ip and on user), bounded to a single
    actor and the selected range."""
    actor_col = RawEvent.user if is_user else RawEvent.client_ip
    conditions = [
        RawEvent.timestamp >= since,
        RawEvent.timestamp <= until,
        actor_col == actor,
        RawEvent.domain.is_not(None),
    ]
    if branch is not None:
        conditions.append(RawEvent.branch == branch)
    if blocked_only:
        conditions.append(RawEvent.blocked.is_(True))
    rows = (
        await session.execute(
            select(
                RawEvent.domain,
                func.count(),
                func.coalesce(func.sum(case((RawEvent.blocked.is_(True), 1), else_=0)), 0),
                func.coalesce(func.sum(RawEvent.bytes), 0),
            )
            .where(*conditions)
            .group_by(RawEvent.domain)
            .order_by(func.count().desc())
            .limit(_ACTOR_TOP_DOMAINS)
        )
    ).all()
    return [
        ActorDomainRow(
            domain=domain or "",
            request_count=int(count),
            blocked_count=int(blocked or 0),
            total_bytes=int(byte_total),
        )
        for domain, count, blocked, byte_total in rows
    ]


async def get_new_entities(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None
) -> NewEntitiesResponse:
    # "New" means "first seen anywhere in the retained history falls inside
    # [since, until]" -- so it looks back over the whole client-aggregate
    # window (minute rows plus the rolled-up hourly rows, ~400 days), not
    # just one window before `since`. A shorter lookback would flag a
    # long-time user who simply had a gap (a weekend, a holiday) as new.
    combined = client_bucket_rows(until - timedelta(days=400), until, branch=branch)

    async def _first_seen_within(col: Any) -> list[str]:
        rows = (
            await session.execute(
                select(col, func.min(combined.c.bucket_ts))
                .where(col.is_not(None), col != "")
                .group_by(col)
                .having(func.min(combined.c.bucket_ts) >= since)
            )
        ).all()
        return [r[0] for r in rows]

    new_users = await _first_seen_within(combined.c.user)
    new_clients = await _first_seen_within(combined.c.client_ip)

    return NewEntitiesResponse(
        since=since,
        until=until,
        new_users=sorted(new_users)[:_NEW_ENTITY_CAP],
        new_clients=sorted(new_clients)[:_NEW_ENTITY_CAP],
        new_users_total=len(new_users),
        new_clients_total=len(new_clients),
    )


# --------------------------------------------------------------------------
# Blocks & policy
# --------------------------------------------------------------------------


async def get_denials(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    granularity: TrendGranularity,
    branch: str | None,
) -> DenialsResponse:
    # Reason split, all from aggregates (no raw_events scan). Squid marks a
    # request `blocked` when its status is 403 or 407, or the result tag is
    # TCP_DENIED* (see log_parser). 403 and 407 are disjoint status codes so
    # `acl_denied + proxy_auth <= total_blocked` always holds and
    # `other_blocked` (the remainder -- TCP_DENIED with status 0, a
    # blacklist redirect, a quota block, ...) is never negative. Do NOT
    # count TCP_DENIED separately: on an auth-enabled deployment every
    # unauthenticated request is logged TCP_DENIED/407, so folding it into
    # "acl_denied" both mislabels auth challenges and double-counts them
    # against proxy_auth.
    http_conditions = [HttpMinuteAggregate.bucket_ts >= since, HttpMinuteAggregate.bucket_ts <= until]
    min_conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= until]
    if branch is not None:
        http_conditions.append(HttpMinuteAggregate.branch == branch)
        min_conditions.append(MinuteAggregate.branch == branch)

    http_rows = (
        await session.execute(
            select(
                HttpMinuteAggregate.bucket_ts,
                HttpMinuteAggregate.status_code,
                func.sum(HttpMinuteAggregate.request_count),
            )
            .where(*http_conditions, HttpMinuteAggregate.status_code.in_([403, 407]))
            .group_by(HttpMinuteAggregate.bucket_ts, HttpMinuteAggregate.status_code)
        )
    ).all()
    total_blocked_rows = (
        await session.execute(
            select(MinuteAggregate.bucket_ts, func.sum(MinuteAggregate.blocked_requests))
            .where(*min_conditions)
            .group_by(MinuteAggregate.bucket_ts)
        )
    ).all()

    forbid_403: dict[datetime, int] = defaultdict(int)
    auth_407: dict[datetime, int] = defaultdict(int)
    for bucket_ts, status_code, count in http_rows:
        if status_code == 403:
            forbid_403[bucket_ts] += int(count)
        else:
            auth_407[bucket_ts] += int(count)
    total_blocked: dict[datetime, int] = {r[0]: int(r[1]) for r in total_blocked_rows}

    grouped: dict[datetime, DenialReasonPoint] = {}
    t_acl = t_auth = t_other = 0
    tmp: dict[datetime, list[int]] = defaultdict(lambda: [0, 0, 0])
    for bucket_ts in set(forbid_403) | set(auth_407) | set(total_blocked):
        acl = forbid_403.get(bucket_ts, 0)
        auth = auth_407.get(bucket_ts, 0)
        other = max(0, total_blocked.get(bucket_ts, 0) - acl - auth)
        key = _truncate(bucket_ts, granularity)
        tmp[key][0] += acl
        tmp[key][1] += auth
        tmp[key][2] += other
        t_acl += acl
        t_auth += auth
        t_other += other
    drop = _drop_in_progress_bucket(list(tmp), granularity)
    for key, (acl, auth, other) in sorted(tmp.items()):
        if key in drop:
            continue
        grouped[key] = DenialReasonPoint(
            bucket_ts=key, acl_denied=acl, proxy_auth=auth, other_blocked=other
        )

    # Top blocked domains / categories / actors -- from the blocked_count
    # columns on the domain and client aggregates.
    dom_conditions = [
        DomainMinuteAggregate.bucket_ts >= since,
        DomainMinuteAggregate.bucket_ts <= until,
    ]
    if branch is not None:
        dom_conditions.append(DomainMinuteAggregate.branch == branch)
    dom_rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.blocked_count),
                func.sum(DomainMinuteAggregate.total_bytes),
            )
            .where(*dom_conditions)
            .group_by(DomainMinuteAggregate.domain)
            .having(func.sum(DomainMinuteAggregate.blocked_count) > 0)
            .order_by(func.sum(DomainMinuteAggregate.blocked_count).desc())
            .limit(15)
        )
    ).all()
    overrides = await get_overrides_map(session)
    top_domains = [
        ActorDomainRow(
            domain=domain, request_count=0, blocked_count=int(blocked), total_bytes=int(tb)
        )
        for domain, blocked, tb in dom_rows
    ]
    cat_totals: dict[DomainCategoryLabel, list[int]] = defaultdict(lambda: [0, 0])
    for domain, blocked, tb in dom_rows:
        cat = effective_category(domain, overrides)
        cat_totals[cat][0] += int(blocked)
        cat_totals[cat][1] += int(tb)
    top_categories = sorted(
        (
            ActorCategorySlice(category=c, request_count=v[0], total_bytes=v[1])
            for c, v in cat_totals.items()
        ),
        key=lambda s: s.request_count,
        reverse=True,
    )

    combined = client_bucket_rows(since, until, branch=branch)
    is_user = await _has_authenticated_users(session, since, until, branch)
    actor_col = combined.c.user if is_user else combined.c.client_ip
    actor_conditions: list[Any] = [actor_col.is_not(None)]
    if is_user:
        actor_conditions.append(actor_col != "")
    actor_rows = (
        await session.execute(
            select(
                actor_col,
                func.sum(combined.c.request_count),
                func.sum(combined.c.blocked_count),
                func.sum(combined.c.total_bytes),
            )
            .where(*actor_conditions)
            .group_by(actor_col)
            .having(func.sum(combined.c.blocked_count) > 0)
            .order_by(func.sum(combined.c.blocked_count).desc())
            .limit(15)
        )
    ).all()
    top_actors = [
        ActorRow(
            actor=actor,
            is_user=is_user,
            request_count=int(req),
            blocked_count=int(blocked),
            blocked_ratio=(int(blocked) / int(req)) if req else 0.0,
            total_bytes=int(tb),
            top_category=None,
        )
        for actor, req, blocked, tb in actor_rows
    ]

    return DenialsResponse(
        granularity=granularity,
        total_denied=t_acl + t_auth + t_other,
        acl_denied=t_acl,
        proxy_auth=t_auth,
        other_blocked=t_other,
        series=list(grouped.values()),
        top_domains=top_domains,
        top_categories=top_categories,
        top_actors=top_actors,
    )


# --------------------------------------------------------------------------
# Ingest health (per branch)
# --------------------------------------------------------------------------


def build_ingest_health(health_snapshot: dict) -> IngestHealthResponse:
    """Reshapes /api/health's log-source slice into the per-branch ingest
    view the Branches tab shows -- so 'full control of Squid' on this page
    includes whether the logs are actually being read."""
    return IngestHealthResponse(
        aggregator_backlog_ratio=float(health_snapshot.get("aggregator_backlog_ratio", 0.0)),
        aggregator_events_likely_lost=bool(
            health_snapshot.get("aggregator_events_likely_lost", False)
        ),
        branches=[
            BranchIngestRow(
                branch=src["branch"],
                tailer_alive=bool(src["alive"]),
                parse_failure_rate=src["parse_failure_rate"],
                lines_seen=int(src["lines_seen"]),
                lines_parsed=int(src["lines_parsed"]),
            )
            for src in health_snapshot.get("log_sources", [])
        ],
    )
