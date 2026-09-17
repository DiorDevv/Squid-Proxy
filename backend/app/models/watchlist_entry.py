import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class WatchlistTargetType(str, enum.Enum):
    CLIENT_IP = "client_ip"
    DOMAIN = "domain"
    USER = "user"


class WatchlistEntry(Base):
    """A client IP, domain or proxy-auth user an admin has flagged to watch.
    A background job (app/services/watchlist_monitor.py) raises an anomaly
    the first time a watched target is active again (subject to a cooldown),
    which then flows through the normal alert pipeline.

    `branch` is `""` for "any branch", or a concrete branch tag to scope the
    watch -- stored as `""` (never NULL) so the unique index below is a
    plain column tuple.
    """

    __tablename__ = "watchlist_entries"
    __table_args__ = (
        Index("ix_watchlist_type_value_branch", "target_type", "value", "branch", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type: Mapped[WatchlistTargetType] = mapped_column(Enum(WatchlistTargetType))
    value: Mapped[str] = mapped_column(String(255), index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    branch: Mapped[str] = mapped_column(String(64), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
    # Last time the target had any logged activity, and last time that
    # raised an anomaly (cooldown anchor) -- see watchlist_monitor.py.
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_alerted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
