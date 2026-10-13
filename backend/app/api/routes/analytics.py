from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    get_db,
    require_admin_or_auditor,
    require_any_role,
    resolve_branch,
)
from app.api.routes.health import build_health_snapshot
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.audit_log import AuditAction
from app.schemas.analytics import (
    ActivityHeatmapResponse,
    AnalyticsOverview,
    BranchBlockedDomainsResponse,
    BranchBreakdownResponse,
    BranchCategoryBreakdownResponse,
    BranchSignalsResponse,
    BranchTrendResponse,
    CategoryTrendResponse,
    RetentionInfo,
    TrendGranularity,
    TrendMetric,
)
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.config_advisor import ConfigAdvisorResponse
from app.schemas.squid_ops import (
    ActorDetailResponse,
    ActorLeaderboardResponse,
    DenialsResponse,
    IngestHealthResponse,
    NewEntitiesResponse,
    ResponseTimeResponse,
    ResultCodeResponse,
)
from app.services import (
    actor_export,
    analytics_service,
    audit_service,
    config_advisor_service,
    retention_settings_service,
    squid_ops_service,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_any_role)])


@router.get("/overview", response_model=AnalyticsOverview)
async def read_overview(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    return await analytics_service.get_overview(db, effective_range.since, effective_range.until, branch)


@router.get("/category-trend", response_model=CategoryTrendResponse)
async def read_category_trend(
    granularity: TrendGranularity = Query(default=TrendGranularity.HOUR),
    metric: TrendMetric = Query(default=TrendMetric.BYTES),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> CategoryTrendResponse:
    return await analytics_service.get_category_trend(
        db, effective_range.since, effective_range.until, granularity, metric, branch
    )


@router.get("/branch-breakdown", response_model=BranchBreakdownResponse)
async def read_branch_breakdown(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchBreakdownResponse:
    return await analytics_service.get_branch_breakdown(
        db, effective_range.since, effective_range.until, branch
    )


@router.get("/branch-signals", response_model=BranchSignalsResponse)
async def read_branch_signals(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchSignalsResponse:
    return await analytics_service.get_branch_signals(
        db, effective_range.since, effective_range.until, branch
    )


@router.get("/branch-trend", response_model=BranchTrendResponse)
async def read_branch_trend(
    granularity: TrendGranularity = Query(default=TrendGranularity.HOUR),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchTrendResponse:
    return await analytics_service.get_branch_trend(
        db, effective_range.since, effective_range.until, granularity, branch
    )


@router.get("/branch-category-breakdown", response_model=BranchCategoryBreakdownResponse)
async def read_branch_category_breakdown(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchCategoryBreakdownResponse:
    return await analytics_service.get_branch_category_breakdown(
        db, effective_range.since, effective_range.until, branch
    )


@router.get("/branch-blocked-domains", response_model=BranchBlockedDomainsResponse)
async def read_branch_blocked_domains(
    limit: int = Query(default=8, ge=1, le=50),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchBlockedDomainsResponse:
    return await analytics_service.get_branch_top_blocked_domains(
        db, effective_range.since, effective_range.until, branch, limit
    )


@router.get("/result-codes", response_model=ResultCodeResponse)
async def read_result_codes(
    granularity: TrendGranularity = Query(default=TrendGranularity.HOUR),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ResultCodeResponse:
    return await squid_ops_service.get_result_codes(
        db, effective_range.since, effective_range.until, granularity, branch
    )


@router.get("/response-time", response_model=ResponseTimeResponse)
async def read_response_time(
    granularity: TrendGranularity = Query(default=TrendGranularity.HOUR),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ResponseTimeResponse:
    return await squid_ops_service.get_response_time(
        db, effective_range.since, effective_range.until, granularity, branch
    )


@router.get("/actors", response_model=ActorLeaderboardResponse)
async def read_actor_leaderboard(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="requests"),
    kind: Literal["all", "user", "ip"] = Query(default="all"),
    search: str | None = Query(default=None, max_length=255),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ActorLeaderboardResponse:
    return await squid_ops_service.get_actor_leaderboard(
        db, effective_range.since, effective_range.until, branch, limit, sort, search,
        offset=offset, kind=kind,
    )


@router.get("/actors/export", dependencies=[Depends(require_admin_or_auditor)])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def export_actor_leaderboard(
    request: Request,
    format: Literal["xlsx", "csv"] = Query(default="xlsx"),
    lang: Literal["uz", "en", "ru"] = Query(default="uz"),
    sort: str = Query(default="requests"),
    kind: Literal["all", "user", "ip"] = Query(default="all"),
    search: str | None = Query(default=None, max_length=255),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """The whole "Who" list (every page) as an Excel or CSV file."""
    rows = await squid_ops_service.list_all_actors(
        db, effective_range.since, effective_range.until, branch, sort, search, kind
    )
    if format == "xlsx":
        content = actor_export.actors_xlsx(
            rows, lang, branch=branch, since=effective_range.since, until=effective_range.until,
            kind=kind, search=search, sort=sort,
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = actor_export.actors_csv(rows, lang)
        media_type = "text/csv; charset=utf-8"
    await audit_service.record(
        db,
        action=AuditAction.EXPORT_CREATED,
        actor_user_id=current_user.user_id,
        branch=branch,
        detail=f"who-list format={format} kind={kind} rows={len(rows)}"
        + (f" search={search}" if search else ""),
    )
    await db.commit()
    stamp = effective_range.until.strftime("%Y%m%d-%H%M")
    filename = f"kim-{branch or 'barcha'}-{stamp}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/actor-detail", response_model=ActorDetailResponse)
async def read_actor_detail(
    actor: str = Query(min_length=1, max_length=255),
    is_user: bool = Query(default=True),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActorDetailResponse:
    result = await squid_ops_service.get_actor_detail(
        db, actor, is_user, effective_range.since, effective_range.until, branch
    )
    await audit_service.record_read_access(
        db,
        action=AuditAction.ANALYTICS_ACTOR_VIEWED,
        actor_user_id=current_user.user_id,
        branch=branch,
        detail=f"{'user' if is_user else 'client_ip'}={actor}",
    )
    return result


@router.get("/new-entities", response_model=NewEntitiesResponse)
async def read_new_entities(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> NewEntitiesResponse:
    return await squid_ops_service.get_new_entities(db, effective_range.since, effective_range.until, branch)


@router.get("/denials", response_model=DenialsResponse)
async def read_denials(
    granularity: TrendGranularity = Query(default=TrendGranularity.HOUR),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> DenialsResponse:
    return await squid_ops_service.get_denials(
        db, effective_range.since, effective_range.until, granularity, branch
    )


@router.get("/retention", response_model=RetentionInfo)
async def read_retention(db: AsyncSession = Depends(get_db)) -> RetentionInfo:
    settings = get_settings()
    retention = await retention_settings_service.get_settings_row(db)
    return RetentionInfo(
        raw_event_days=retention.raw_events_days,
        aggregate_days=settings.RETENTION_DAYS_AGGREGATES,
        ops_aggregate_days=settings.RETENTION_DAYS_OPS_AGGREGATES,
    )


@router.get("/config-advisor", response_model=ConfigAdvisorResponse)
async def read_config_advisor(
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ConfigAdvisorResponse:
    """Heuristic checks over the last 24h of aggregates for common Squid
    misconfigurations (no caching, no proxy auth, nothing ever denied,
    sensitive categories allowed through, one domain dominating). Empty
    `findings` for a well-configured, well-fed deployment."""
    return await config_advisor_service.analyze(db, branch)


@router.get("/ingest-health", response_model=IngestHealthResponse)
async def read_ingest_health(request: Request) -> IngestHealthResponse:
    """Per-branch log-ingestion health (tailer alive, parse failure rate,
    aggregator backlog) -- the same numbers /api/health reports, reshaped
    for the Analytics Branches view so 'full Squid control' on this page
    includes whether the logs are actually being read."""
    return squid_ops_service.build_ingest_health(build_health_snapshot(request.app))


@router.get("/activity-heatmap", response_model=ActivityHeatmapResponse)
async def read_activity_heatmap(
    blocked_only: bool = Query(default=False),
    tz_offset_minutes: int = Query(
        default=0,
        ge=-840,
        le=840,
        description="Minutes east of UTC to bucket weekday/hour in (0 = UTC).",
    ),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ActivityHeatmapResponse:
    return await analytics_service.get_activity_heatmap(
        db, effective_range.since, effective_range.until, branch, blocked_only, tz_offset_minutes
    )
