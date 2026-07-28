import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class ExportJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportJob(Base):
    """A background CSV/JSON export request (see api/routes/export.py and
    services/export_job_service.py).

    GET /api/export streams synchronously, which ties up the requesting
    browser tab for as long as the range takes to fully export -- fine for
    a quick pull, unworkable for a full week at real traffic volumes
    (minutes, hundreds of MB). This table lets that work happen
    server-side instead: a job is created (PENDING), a background task
    runs it (RUNNING -> DONE/FAILED, writing the result to a file under
    EXPORT_JOBS_DIR), and the client polls status instead of holding a
    connection open the whole time.
    """

    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[ExportJobStatus] = mapped_column(
        Enum(ExportJobStatus), default=ExportJobStatus.PENDING, index=True
    )
    format: Mapped[str] = mapped_column(String(8))
    since: Mapped[datetime] = mapped_column(UTCDateTime)
    until: Mapped[datetime] = mapped_column(UTCDateTime)
    blocked_only: Mapped[bool] = mapped_column(Boolean, default=False)
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True)

    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Set on the first successful download (see export_job_service.record_download).
    # None means "never downloaded" -- what the undownloaded-export monitor
    # (app/services/undownloaded_export_monitor.py) and AFTER_DOWNLOAD
    # cleanup mode (ExportSettings) both key off.
    downloaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
