from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role, resolve_branch
from app.api.routes.health import build_health_snapshot
from app.schemas.analytics import (
    ActivityHeatmapResponse,
    AnalyticsOverview,
    BranchBreakdownResponse,
    BranchRiskResponse,
    CategoryTrendResponse,
    TrendGranularity,
    TrendMetric,
)
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.config_advisor import ConfigAdvisorResponse
from app.schemas.squid_ops import (
    ActorDetailResponse,
    ActorLeaderboardResponse,
    DenialsResponse,
    HierarchyResponse,
    HttpBreakdownResponse,
    IngestHealthResponse,
    NewEntitiesResponse,
    ResponseTimeResponse,
    ResultCodeResponse,
)
from app.services import analytics_service, config_advisor_service, squid_ops_service

router = APIRouter(
    prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_any_role)]
)


@router.get("/overview", response_model=AnalyticsOverview)
async def read_overview(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    return await analytics_service.get_overview(
        db, effective_range.since, effective_range.until, branch
    )


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


@router.get("/branch-risk", response_model=BranchRiskResponse)
async def read_branch_risk(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> BranchRiskResponse:
    return await analytics_service.get_branch_risk(
        db, effective_range.since, effective_range.until, branch
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


@router.get("/http-breakdown", response_model=HttpBreakdownResponse)
async def read_http_breakdown(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> HttpBreakdownResponse:
    return await squid_ops_service.get_http_breakdown(
        db, effective_range.since, effective_range.until, branch
    )


@router.get("/hierarchy", response_model=HierarchyResponse)
async def read_hierarchy(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> HierarchyResponse:
    return await squid_ops_service.get_hierarchy_breakdown(
        db, effective_range.since, effective_range.until, branch
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
    sort: str = Query(default="requests"),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ActorLeaderboardResponse:
    return await squid_ops_service.get_actor_leaderboard(
        db, effective_range.since, effective_range.until, branch, limit, sort
    )


@router.get("/actor-detail", response_model=ActorDetailResponse)
async def read_actor_detail(
    actor: str = Query(min_length=1, max_length=255),
    is_user: bool = Query(default=True),
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> ActorDetailResponse:
    return await squid_ops_service.get_actor_detail(
        db, actor, is_user, effective_range.since, effective_range.until, branch
    )


@router.get("/new-entities", response_model=NewEntitiesResponse)
async def read_new_entities(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> NewEntitiesResponse:
    return await squid_ops_service.get_new_entities(
        db, effective_range.since, effective_range.until, branch
    )


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
