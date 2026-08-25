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
    ALERT_SETTINGS_UPDATED = "alert_settings_updated"
    DOMAIN_CATEGORY_SET = "domain_category_set"
    # One entry per import call, not one per row -- see
    # domain_category_service.import_from_csv, which batches the writes
    # themselves for the same reason (a large import shouldn't mean
    # thousands of near-identical audit rows for what's one admin action).
    DOMAIN_CATEGORY_IMPORTED = "domain_category_imported"
    EXPORT_SETTINGS_UPDATED = "export_settings_updated"
    EXPORT_CANCELLED = "export_cancelled"
    EXPORT_SHARE_REVOKED = "export_share_revoked"
    REPORT_SENT_NOW = "report_sent_now"
    USER_BRANCH_CHANGED = "user_branch_changed"
    TOTP_ENABLED = "totp_enabled"
    TOTP_DISABLED = "totp_disabled"
    TOTP_RECOVERY_CODE_USED = "totp_recovery_code_used"
    # A branch's or the super-admin's Telegram chat linked via a pairing
    # code -- see app/services/telegram_link_service.py. Distinct from
    # ALERT_SETTINGS_UPDATED (a manual PUT /api/alert-settings save).
    TELEGRAM_LINKED = "telegram_linked"


class AuditLogEntry(Base):
    """Who-did-what trail for admin actions (user management, export
    lifecycle, alert/domain-category/export settings, scheduled reports --
    see app/services/audit_service.py for the write side and AuditAction
    above for the full list of what's covered).

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
    # None means the action wasn't confined to one branch -- either the
    # affected resource has no branch dimension at all (domain categories,
    # export settings), or the actor was unrestricted and the action reached
    # across every branch (e.g. an "all branches" report run). Either way
    # every admin, branch-scoped or not, is entitled to see it: the entries
    # that must stay hidden from a branch-scoped admin are exactly the ones
    # tagged with *another* branch (see audit_service.list_entries).
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_email: Mapped[str] = mapped_column(String(255))
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
