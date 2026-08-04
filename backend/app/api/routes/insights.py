from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_any_role, resolve_branch
from app.schemas.common import Page
from app.schemas.insights import AnomalyEventOut
from app.services import insights_service

router = APIRouter(prefix="/api", tags=["insights"], dependencies=[Depends(require_any_role)])


@router.get("/insights/recent", response_model=Page[AnomalyEventOut])
async def read_recent_insights(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> Page[AnomalyEventOut]:
    return await insights_service.list_recent(db, limit, offset, branch)
