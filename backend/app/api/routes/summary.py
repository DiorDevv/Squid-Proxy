from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role, resolve_branch
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.summary import CacheEfficiencyResponse, SummaryResponse
from app.services.stats_service import get_cache_efficiency, get_summary

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary", response_model=SummaryResponse, dependencies=[Depends(require_any_role)])
async def read_summary(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    return await get_summary(
        db, effective_range.since, effective_range.until, effective_range.range, branch
    )


@router.get(
    "/cache-efficiency", response_model=CacheEfficiencyResponse, dependencies=[Depends(require_any_role)]
)
async def read_cache_efficiency(
    effective_range: EffectiveRange = Depends(resolve_range),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> CacheEfficiencyResponse:
    return await get_cache_efficiency(db, effective_range.since, effective_range.until, branch)
