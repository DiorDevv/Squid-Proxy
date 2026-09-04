from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role, resolve_branch
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
from app.services import analytics_service

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
