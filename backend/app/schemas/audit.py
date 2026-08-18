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
