from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.summary import SummaryResponse
from app.services.stats_service import get_summary

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary", response_model=SummaryResponse, dependencies=[Depends(require_any_role)])
async def read_summary(
    effective_range: EffectiveRange = Depends(resolve_range),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    return await get_summary(db, effective_range.since, effective_range.until, effective_range.range)
