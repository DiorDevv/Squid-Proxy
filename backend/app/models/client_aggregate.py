from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_BRANCH
from app.models.db import Base
from app.models.types import UTCDateTime


class ClientMinuteAggregate(Base):
    """Per-minute, per-client (IP + user) counts. Backs the /api/clients listing.

    The true uniqueness constraint on the aggregator's upsert key
    (bucket_ts, client_ip, branch, coalesce(user, '')) is a *expression*
    index, which SQLAlchemy's declarative __table_args__ can't reference
    cleanly before the columns exist as bound attributes -- it's created via
    raw DDL in the `client_minute_aggregate_unique` migration instead (see
    app/db/migrations/versions/). `user` is nullable (anonymous clients), and
    plain SQL unique constraints treat NULL as distinct from itself, which is
    why the migration coalesces it to '' rather than using a plain column
    tuple.
    """

    __tablename__ = "client_minute_aggregates"
    __table_args__ = (Index("ix_client_bucket_ip", "bucket_ts", "client_ip"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    client_ip: Mapped[str] = mapped_column(String(45), index=True)
    branch: Mapped[str] = mapped_column(String(64), default=DEFAULT_BRANCH, index=True)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
