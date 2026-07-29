import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class AuditAction(str, enum.Enum):
    USER_CREATED = "user_created"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_PASSWORD_RESET = "user_password_reset"
    USER_DELETED = "user_deleted"
    EXPORT_CREATED = "export_created"
    EXPORT_DOWNLOADED = "export_downloaded"
    # A share link (see export_job_service.create_share_link) is neither of
    # the above -- distinct from EXPORT_CREATED (queuing the underlying job)
    # so an admin reviewing the audit log can tell "someone ran this export"
    # apart from "someone made this export downloadable without a login."
    EXPORT_SHARED = "export_shared"


class AuditLogEntry(Base):
    """Who-did-what trail for admin user-management actions (see
    app/services/audit_service.py, called from app/services/user_service.py).

    No foreign key to `users` on purpose: the entry must outlive the account
    it describes (e.g. "user_deleted" rows would otherwise dangle or force a
    cascade delete that erases the very record compliance needs), so actor
    and target identity are captured as plain denormalized strings at write
    time instead.
    """

    __tablename__ = "audit_log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, index=True, default=lambda: datetime.now(UTC)
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_email: Mapped[str] = mapped_column(String(255))
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
