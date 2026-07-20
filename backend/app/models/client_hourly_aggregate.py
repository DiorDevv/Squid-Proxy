from datetime import datetime

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class ClientHourlyAggregate(Base):
    """Per-hour, per-client (IP + user) counts -- same shape as
    ClientMinuteAggregate, coarser granularity.

    RetentionJob compresses minute rows older than CLIENT_ROLLUP_AFTER_HOURS
    into rows here, then deletes the source minute rows (see retention.py).
    A client_ip's minute and hourly rows never cover the same point in time
    -- client_service.list_clients/get_client_summary read both tables via
    UNION ALL and rely on that non-overlap, not on one table always winning.
    This exists because "last 7/30 days" queries over
    client_minute_aggregates would otherwise mean GROUP BY over one row per
    client per minute for the whole window -- fine at demo scale, not once
    client count and retention both grow.

    No plain (bucket_ts, client_ip) index: the unique index created in the
    migration (bucket_ts, client_ip, branch, coalesce(user, '')) already
    leads with those same columns.
    """

    __tablename__ = "client_hourly_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    client_ip: Mapped[str] = mapped_column(String(45), index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
