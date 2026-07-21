from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class ArchiveRun(Base):
    """Tracks the latest successful scripts/archive_weekly_export.py run per
    branch (one row each, upserted by branch), so retention.py can tell
    whether the raw_events it's about to permanently delete were ever
    archived, and warn if not -- see RetentionJob.purge().
    """

    __tablename__ = "archive_runs"

    branch: Mapped[str] = mapped_column(String(64), primary_key=True)
    archived_until: Mapped[datetime] = mapped_column(UTCDateTime)
