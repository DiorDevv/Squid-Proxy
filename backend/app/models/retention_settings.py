from datetime import UTC, datetime

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class RetentionSettings(Base):
    """Admin-tunable data-retention policy (Settings -> Retention). Only the
    two knobs that actually get adjusted are here; the rest
    (RETENTION_DAYS_AGGREGATES / _OPS_AGGREGATES / _SYSTEM_EVENTS,
    CLIENT_ROLLUP_AFTER_HOURS, ARCHIVE_KEEP_DAYS) stay env-only -- they're
    set-once and never touched. Singleton row (id always 1), same shape as
    ExportSettings.

    The env var RETENTION_DAYS_RAW_EVENTS seeds this on first read; after an
    admin saves once, this row is authoritative and the env var is inert.
    """

    __tablename__ = "retention_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # How many days of full per-request detail (raw_events) stay queryable
    # before RetentionJob purges them. Lowering this permanently deletes the
    # now-out-of-window rows on the next purge.
    raw_events_days: Mapped[int] = mapped_column(Integer)
    # None (default) = off. When set, RetentionJob skips the raw_events
    # purge for any branch whose most recent successful archive_run is older
    # than this many days, and raises an operator alert -- so a broken
    # archiving job can't quietly take detail down with it. Bounded-disk
    # deployments leave this off; a compliance deployment sets it.
    halt_purge_if_archive_lag_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
