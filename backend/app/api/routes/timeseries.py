from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role
from app.schemas.common import EffectiveRange, Granularity, resolve_range
from app.schemas.timeseries import TimeseriesResponse
from app.services.stats_service import get_timeseries

router = APIRouter(prefix="/api", tags=["timeseries"])


@router.get("/timeseries", response_model=TimeseriesResponse, dependencies=[Depends(require_any_role)])
async def read_timeseries(
    effective_range: EffectiveRange = Depends(resolve_range),
    granularity: Granularity = Query(default=Granularity.MINUTE),
    db: AsyncSession = Depends(get_db),
) -> TimeseriesResponse:
    return await get_timeseries(db, effective_range.since, effective_range.until, granularity)
