from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_or_auditor
from app.schemas.system_health import SystemHealthResponse
from app.services import system_health_service

router = APIRouter(prefix="/api", tags=["system-health"], dependencies=[Depends(require_admin_or_auditor)])


@router.get("/system-health", response_model=SystemHealthResponse)
async def read_system_health(request: Request, db: AsyncSession = Depends(get_db)) -> SystemHealthResponse:
    """One operational snapshot for Settings -> System health: database size
    and growth, disk free, per-branch ingestion, background-job health,
    backup / off-site status (from the jobs' own status files), and the
    recent operational-failure log. Admin/auditor only."""
    return await system_health_service.build(request.app, db)
