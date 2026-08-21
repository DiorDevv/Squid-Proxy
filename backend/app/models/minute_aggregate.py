from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class MinuteAggregate(Base):
    """Per-minute traffic totals, per branch. Backs /api/summary and /api/timeseries."""

    __tablename__ = "minute_aggregates"
    __table_args__ = (
        # bucket_ts alone used to be unique (one branch, one global total per
        # minute); now one row per (bucket_ts, branch) so different branches'
        # totals for the same minute don't collide into a single row.
        Index("ix_minute_bucket_branch", "bucket_ts", "branch", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    blocked_requests: Mapped[int] = mapped_column(Integer, default=0)
    allowed_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    # Squid's %Ss result tag (RawEvent.action) contains "HIT" for anything
    # served from cache (TCP_HIT, TCP_MEM_HIT, TCP_IMS_HIT, ...) and "MISS"
    # for anything fetched fresh (TCP_MISS, TCP_REFRESH_MODIFIED, ...) --
    # see app/services/aggregator.py's _is_cache_hit/_is_cache_miss. Denied/
    # tunneled/other requests count toward neither, since "did the cache
    # help" isn't a meaningful question for those -- see
    # stats_service.get_cache_efficiency, which divides hit_requests by
    # (hit_requests + miss_requests), not by total_requests.
    hit_requests: Mapped[int] = mapped_column(Integer, default=0)
    miss_requests: Mapped[int] = mapped_column(Integer, default=0)
