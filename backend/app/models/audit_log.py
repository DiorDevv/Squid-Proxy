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
    # Read-access trail (docs/PRODUCT.md #1): for a tool whose job is
    # watching people, *who looked at whom* must itself be on the record.
    # One entry per view of a specific subject's activity, per event search,
    # and per per-actor analytics drill-down.
    CLIENT_ACTIVITY_VIEWED = "client_activity_viewed"
    EVENT_SEARCH_RUN = "event_search_run"
    ANALYTICS_ACTOR_VIEWED = "analytics_actor_viewed"
    # A subject-access dossier (docs/PRODUCT.md #4: everything this
    # deployment knows about one client IP or user, in one signed document)
    # was generated -- see app/services/subject_access_service.py. Not
    # deduplicated like the other read-access actions above: producing a
    # dossier is a deliberate, occasional act (unlike paging through a
    # client's activity), so every one is worth its own record.
    SUBJECT_DOSSIER_EXPORTED = "subject_dossier_exported"


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
    # Tamper-evidence: entry_hash = SHA-256 over this row's fields plus the
    # previous entry's entry_hash (see audit_service.compute_entry_hash).
    # Any row that is altered, inserted between two others, or deleted
    # breaks the chain from that point on, and audit_service.verify_chain /
    # scripts/verify_audit_chain.py surface exactly where. prev_hash is
    # None only for the very first entry ever written. Both are nullable in
    # the schema so rows written before this feature (and backfilled by the
    # migration) don't need a non-null default they never had.
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
