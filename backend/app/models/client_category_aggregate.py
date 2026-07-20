from datetime import datetime

from sqlalchemy import BigInteger, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.domain_category import DomainCategoryLabel
from app.models.types import UTCDateTime


class ClientCategoryMinuteAggregate(Base):
    """Per-minute, per-client, per-category request/byte counts.

    Populated inside Aggregator.flush() alongside the other per-minute
    buckets (see aggregator.py) rather than computed after the fact from
    raw_events -- CategoryUsageMonitorJob used to recompute session-based
    "time spent per category" from scratch per client per check, which
    meant one full raw_events scan per active client every check interval.
    That's O(active_clients) full-table scans and doesn't hold up once
    client counts get large; this table lets the monitor do one aggregate
    query across all clients instead (see category_usage_monitor.py).

    "Time spent" here is approximated as distinct minute-buckets with
    activity in that category, not exact session reconstruction -- a
    reasonable proxy for alerting purposes. The precise, session-based
    per-domain breakdown a human reviews for one specific client (see
    time_spent_service.py) is unaffected and still reads from raw_events.
    """

    __tablename__ = "client_category_minute_aggregates"
    __table_args__ = (
        Index(
            "ix_client_category_bucket_ip_category",
            "bucket_ts",
            "client_ip",
            "category",
            "branch",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    client_ip: Mapped[str] = mapped_column(String(45), index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    category: Mapped[DomainCategoryLabel] = mapped_column(Enum(DomainCategoryLabel))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
