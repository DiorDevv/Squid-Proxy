import enum
from datetime import UTC, datetime

from sqlalchemy import Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class ExportCleanupMode(str, enum.Enum):
    # Files (and their ExportJob row's file_path) are deleted once they're
    # older than retention_hours, downloaded or not -- the original,
    # always-on behavior (formerly the hardcoded EXPORT_JOB_RETENTION_HOURS
    # setting).
    TIME_BASED = "time_based"
    # Deleted the moment they're successfully downloaded, regardless of age
    # -- for a deployment tight on disk that would rather not hold a copy
    # around at all once it's been retrieved. Mutually exclusive with
    # time-based retention: a job that's *never* downloaded in this mode is
    # never auto-deleted by age (the undownloaded-export monitor is what
    # surfaces that, not this).
    AFTER_DOWNLOAD = "after_download"


class ExportSettings(Base):
    """Admin-tunable export-job cleanup policy (see
    app/services/export_job_service.py's purge_old_jobs and the download
    route). Global, not per-branch -- unlike AlertSettings, disk usage from
    export files isn't a per-branch concern. Singleton row (id always 1),
    same reasoning AlertSettings' per-branch row gives for not being a
    generic key-value table: a handful of fields, each its own type.
    """

    __tablename__ = "export_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cleanup_mode: Mapped[ExportCleanupMode] = mapped_column(
        Enum(ExportCleanupMode), default=ExportCleanupMode.TIME_BASED
    )
    # 120h (5 days) rather than a plain 2 days: an export queued Friday
    # afternoon and picked up the following Monday morning is already ~64h
    # later -- a 48h window silently loses exactly that common case. 5 days
    # comfortably survives a weekend (or a short absence) with margin, at
    # the cost of files sitting on disk a few days longer; deployments tight
    # on disk can still lower this (or switch to AFTER_DOWNLOAD) themselves.
    retention_hours: Mapped[int] = mapped_column(Integer, default=120)
    # None means off -- no warning raised. Applies in both cleanup modes:
    # in TIME_BASED it doubles as "warn before this job is auto-deleted";
    # in AFTER_DOWNLOAD there's no scheduled deletion to warn ahead of, so
    # it just means "warn once a DONE job has sat undownloaded this long".
    #
    # No column-level default here, deliberately -- SQLAlchemy's client-side
    # `default=` fires on INSERT whenever the bound value is None, with no
    # way to tell "never set" apart from "explicitly set to None"; on a
    # nullable column where None is itself a meaningful, admin-choosable
    # state (off), a non-None default here would silently overwrite an
    # admin's first-ever PUT /api/export-settings choosing "off" back to
    # "on" (verified: an explicit `= None` on a brand-new row is replaced by
    # the column default at flush, the same override does NOT happen on an
    # UPDATE to an already-persisted row). The effective out-of-the-box
    # default (24h, "on") instead lives purely in
    # export_settings_service.DEFAULT_WARN_UNDOWNLOADED_AFTER_HOURS,
    # applied only to the unsaved in-memory row get_settings_row() returns
    # before any row has ever been persisted -- the same "no row inserted
    # just to be read from" pattern the module docstring already describes.
    warn_undownloaded_after_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
