import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class UserRole(str, enum.Enum):
    # The only role that manages admins/auditors/other super admins, and
    # always unrestricted (branch is None) -- see
    # app/services/user_service.py. Satisfies every "admin" check too (see
    # api/deps.require_admin).
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    VIEWER = "viewer"
    # Read-only oversight: everything a viewer sees, plus the audit log and
    # the data-retention/policy surface, minus every mutation. The role a
    # compliance function occupies -- it can review who looked at whom
    # without being able to change users, settings, or data. See
    # app/api/deps.py (require_admin_or_auditor) and docs/PRODUCT.md.
    AUDITOR = "auditor"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The login name -- always stored lowercased (see
    # user_service.normalize_username), so uniqueness is effectively
    # case-insensitive on every backend.
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Optional contact address only -- no longer used to sign in.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    # None (the default) means unrestricted -- every user has this today.
    # Set to one of Settings.effective_log_sources' branch tags to restrict
    # this account to that branch's data only (see api/deps.py's
    # resolve_branch) -- a viewer at one office/site who shouldn't see
    # other branches' traffic, not a privilege level like role above.
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Bumped whenever every existing session of this account must be
    # invalidated at once -- a role or branch change, a password reset (see
    # app/services/user_service.py). Every access token carries the value
    # it was minted with as its `tv` claim; api/deps.get_current_user
    # rejects a token whose `tv` no longer matches this row, so a
    # deprovision/demote takes effect on the very next request instead of
    # lingering for the whole ACCESS_TOKEN_EXPIRE_MINUTES window.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
    # Set as soon as TOTP setup begins (app/services/totp_service.py.
    # begin_setup), but not trusted for login until totp_enabled is True --
    # a setup flow abandoned partway through (scanned the QR, never entered
    # a code) must not leave the account silently protected by a secret the
    # admin never actually confirmed working.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Accounts are deactivated, never deleted, so the audit trail keeps a
    # live row to point at. An inactive account can't sign in, and its
    # token_version is bumped on deactivation so every session dies at once.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    # Set on every account an admin creates or resets -- the generated
    # temporary password is shown once, and api/deps.get_current_user
    # refuses everything except changing it until the user has.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Username of whoever created this account (None for bootstrap/CLI).
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class PasswordHistory(Base):
    """Previous password hashes, newest PASSWORD_HISTORY kept per user --
    a user changing their own password may not reuse any of them (see
    user_service.change_own_password)."""

    __tablename__ = "password_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
