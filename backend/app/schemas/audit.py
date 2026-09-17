from datetime import datetime

from pydantic import BaseModel

from app.models.audit_log import AuditAction


class AuditLogEntryOut(BaseModel):
    id: str
    created_at: datetime
    action: AuditAction
    branch: str | None
    actor_email: str
    target_email: str | None
    detail: str | None


class AuditChainBreak(BaseModel):
    id: str
    position: int
    created_at: str
    reason: str


class AuditChainVerifyResponse(BaseModel):
    ok: bool
    entries_checked: int
    broken_at: AuditChainBreak | None = None
