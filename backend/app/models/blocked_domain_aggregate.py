"""Hourly per-domain block counts behind the Blocked page's "Domains" view.

Grouping raw_events by domain is too slow for an interactive page (a week is
~30M blocked rows, ~10s even for 24h), and domain_minute_aggregates can't
answer it: it has no proxy dimension and lumps a real ACL denial together
with a 407 (proxy login required), which is not a block at all.

Two tables, both filled by Aggregator.flush() in hour buckets (sum-upserted
across flushes, like every other aggregate):

  - blocked_domain_hourly_aggregates: (hour, branch, proxy, domain) ->
    denied / auth counts. Small (~35k rows/day) -- the list, its paging and
    sorting all run here.
  - blocked_domain_client_hourly_aggregates: the same plus client_ip. Larger
    (~500k rows/day); only read for one page's domains at a time (the
    "clients" column) or for an export, never scanned to build the list.

`proxy` is stored as "" (never NULL) for sources without a LogSource.proxy
label, so the unique indexes stay plain column tuples. "denied" is every
blocked event except a 407; "auth" is the 407s (see log_parser's `blocked`).
"""

from datetime import datetime

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class BlockedDomainHourlyAggregate(Base):
    __tablename__ = "blocked_domain_hourly_aggregates"
    __table_args__ = (
        Index(
            "ix_blocked_domain_hourly_key", "bucket_ts", "branch", "proxy", "domain", unique=True
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH)
    proxy: Mapped[str] = mapped_column(String(64), default="")
    domain: Mapped[str] = mapped_column(String(255), index=True)
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    auth_count: Mapped[int] = mapped_column(Integer, default=0)


class BlockedDomainClientHourlyAggregate(Base):
    __tablename__ = "blocked_domain_client_hourly_aggregates"
    __table_args__ = (
        Index(
            "ix_blocked_domain_client_hourly_key",
            "bucket_ts",
            "branch",
            "proxy",
            "domain",
            "client_ip",
            unique=True,
        ),
        # The per-page client count looks rows up by domain first.
        Index("ix_blocked_domain_client_hourly_domain_ts", "domain", "bucket_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH)
    proxy: Mapped[str] = mapped_column(String(64), default="")
    domain: Mapped[str] = mapped_column(String(255))
    client_ip: Mapped[str] = mapped_column(String(45))
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    auth_count: Mapped[int] = mapped_column(Integer, default=0)
