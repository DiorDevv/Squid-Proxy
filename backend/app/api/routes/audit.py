from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_or_auditor, resolve_branch
from app.schemas.audit import AuditChainBreak, AuditChainVerifyResponse, AuditLogEntryOut
from app.schemas.common import Page
from app.services import audit_service

router = APIRouter(prefix="/api", tags=["audit"], dependencies=[Depends(require_admin_or_auditor)])


@router.get("/audit-log", response_model=Page[AuditLogEntryOut])
async def read_audit_log(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
) -> Page[AuditLogEntryOut]:
    return await audit_service.list_entries(db, limit, offset, branch=branch)


@router.get("/audit-log/verify", response_model=AuditChainVerifyResponse)
async def verify_audit_log(db: AsyncSession = Depends(get_db)) -> AuditChainVerifyResponse:
    """Recompute the audit log's hash chain end to end (see
    AuditLogEntry.entry_hash). `ok: false` with `broken_at` set means a row
    was altered, inserted, or deleted at or before that position -- someone
    with database access rewriting history. Not branch-scoped: the chain is
    one sequence across every branch, and a broken link anywhere is
    everyone's problem. scripts/verify_audit_chain.py runs the same check
    from outside the app."""
    result = await audit_service.verify_chain(db)
    return AuditChainVerifyResponse(
        ok=result.ok,
        entries_checked=result.entries_checked,
        broken_at=AuditChainBreak(**result.broken_at) if result.broken_at else None,
    )
