import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
    # One sign-in = one session: every token rotated forward from the same
    # login shares this id (see routes/auth.refresh), so it's what the
    # session list shows and what revoking "a session" revokes. Access
    # tokens carry it as their `sid` claim.
    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, default=lambda: str(uuid.uuid4())
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # When this session first signed in -- carried across rotations, unlike
    # created_at (which is per-token).
    session_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Last time this session's user re-entered their password (login counts)
    # -- sensitive user-management actions require it within
    # REAUTH_MINUTES, see api/deps.require_reauth.
    reauth_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
