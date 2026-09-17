import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class UserRole(str, enum.Enum):
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
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
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
