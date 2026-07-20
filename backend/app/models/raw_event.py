from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class RawEvent(Base):
    """Durable per-event detail, retained for a shorter window than aggregates.

    Backs /api/clients/{id}/activity and /api/export for ranges beyond the
    in-memory ring buffer's window.
    """

    __tablename__ = "raw_events"
    __table_args__ = (
        # Leads with client_ip (not timestamp) because every hot per-client
        # query filters on client_ip equality first (see the migration
        # 8a1d3f6c9b02_raw_events_client_ts_index docstring for the measured
        # rationale) -- `timestamp` alone still has its own index below for
        # range-only queries (e.g. retention's purge-by-age).
        Index("ix_raw_events_client_ts", "client_ip", "timestamp"),
        Index("ix_raw_events_ts_domain", "timestamp", "domain"),
        # Serves get_events'/export's WHERE blocked = ? AND timestamp
        # BETWEEN ? AND ? ORDER BY timestamp DESC (see migration
        # 2b9c6a3ff517 for the measured rationale).
        Index("ix_raw_events_ts_blocked", "timestamp", "blocked"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    client_ip: Mapped[str] = mapped_column(String(45), index=True)
    action: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    hierarchy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    peer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, index=True)
