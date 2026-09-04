"""Per-minute Squid-operational aggregates behind the Analytics section's
"Traffic & cache", "Blocks" and "Who" views.

All four tables follow the same shape as `minute_aggregates` /
`domain_minute_aggregates`: one row per (bucket_ts, branch, <dimension...>),
minute granularity kept for the table's whole (shorter,
`RETENTION_DAYS_OPS_AGGREGATES`) retention window -- no hourly rollup. They
are populated in the same `Aggregator.flush()` pass as every other bucket,
off one shared scan of the flushed events, so they can never drift from
`minute_aggregates`.

The `user` dimension is stored as `""` (never NULL) for unauthenticated
traffic, so every unique index here is a plain column tuple -- no
`COALESCE(...)` expression index like the older client tables need.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.domain_category import DomainCategoryLabel
from app.models.types import UTCDateTime


class ResultCodeMinuteAggregate(Base):
    """Per-minute request/byte counts by Squid result code (the `%Ss` tag,
    e.g. TCP_HIT, TCP_MISS, TCP_DENIED, TCP_TUNNEL). The headline
    operational signal for a Squid deployment -- cache effectiveness, deny
    volume, tunnel share -- at a glance."""

    __tablename__ = "result_code_minute_aggregates"
    __table_args__ = (
        Index("ix_result_code_bucket_branch_action", "bucket_ts", "branch", "action", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    action: Mapped[str] = mapped_column(String(64))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class HttpMinuteAggregate(Base):
    """Per-minute request/byte counts by (HTTP method, response status
    code). Backs the method mix and the status-class breakdown, including
    403 (ACL deny) and 407 (proxy auth required) called out on the Blocks
    view. status_code is 0 when Squid logged `-`."""

    __tablename__ = "http_minute_aggregates"
    __table_args__ = (
        Index(
            "ix_http_bucket_branch_method_status",
            "bucket_ts",
            "branch",
            "method",
            "status_code",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    method: Mapped[str] = mapped_column(String(16))
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class HierarchyMinuteAggregate(Base):
    """Per-minute request/byte counts by Squid hierarchy code (the part of
    the hierarchy field before the `/`, e.g. HIER_DIRECT, DEFAULT_PARENT,
    FIRSTUP_PARENT) -- where requests actually resolved. `-` is normalized
    to "NONE"."""

    __tablename__ = "hierarchy_minute_aggregates"
    __table_args__ = (
        Index("ix_hierarchy_bucket_branch_code", "bucket_ts", "branch", "hierarchy_code", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    hierarchy_code: Mapped[str] = mapped_column(String(64))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class UserCategoryMinuteAggregate(Base):
    """Per-minute request/byte counts by (proxy-auth user, effective domain
    category). Powers the per-user category split and "top category" column
    on the "Who" view. `user` is `""` for unauthenticated traffic (Squid
    logged `-`); where a deployment doesn't use proxy auth this table is
    just one `""` bucket per category and the IP-centric
    `client_category_minute_aggregates` carries the detail instead."""

    __tablename__ = "user_category_minute_aggregates"
    __table_args__ = (
        Index(
            "ix_user_category_bucket_branch_user_category",
            "bucket_ts",
            "branch",
            "user",
            "category",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    user: Mapped[str] = mapped_column(String(255), default="", index=True)
    category: Mapped[DomainCategoryLabel] = mapped_column(Enum(DomainCategoryLabel))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
