from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.schemas.audit import AuditLogEntryOut
from app.schemas.common import Page
from app.services import audit_service

router = APIRouter(prefix="/api", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("/audit-log", response_model=Page[AuditLogEntryOut])
async def read_audit_log(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[AuditLogEntryOut]:
    return await audit_service.list_entries(db, limit, offset)
