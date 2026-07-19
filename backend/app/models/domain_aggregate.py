from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class DomainMinuteAggregate(Base):
    """Per-minute, per-domain counts. Backs /api/top-domains and /api/top-blocked."""

    __tablename__ = "domain_minute_aggregates"
    __table_args__ = (
        # Unique, not just indexed: the aggregator's select-then-increment
        # upsert relies on at most one row per (bucket_ts, domain) existing.
        # A future multi-instance aggregator or a duplicate flush would
        # otherwise silently create a second row and split/undercount stats
        # instead of failing loudly.
        Index("ix_domain_bucket_domain", "bucket_ts", "domain", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
