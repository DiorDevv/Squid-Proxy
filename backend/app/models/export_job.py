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
    # Narrower filters than blocked_only/branch above -- all optional, all
    # resolved the same way get_events'/GET /api/export's own filters are
    # (see event_query_service.build_event_conditions). Stored on the job
    # row (not just applied once at query time) so list_jobs/the UI can show
    # *what* a past job was scoped to, the same reason blocked_only/branch
    # are already columns instead of being discarded after the query ran.
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # Comma-separated subset of export_service.EXPORT_COLUMNS, in the order
    # the admin picked -- None means "every column" (the long-standing
    # default). A dedicated join-table would be overkill for what's really
    # just an ordered list of ~12 known-safe identifiers.
    columns: Mapped[str | None] = mapped_column(String(255), nullable=True)

    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # SHA-256 of the finished result file (zip or xlsx), set once run_job
    # reaches DONE -- lets whoever receives the export (directly or via a
    # share link) prove afterwards it's byte-identical to what this server
    # actually produced, the same chain-of-custody concern
    # scripts/backup_database.py's restore docs raise for DB backups.
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Time-limited, admin-issued link so a finished export can be handed to
    # someone without a dashboard login (e.g. legal/compliance) without
    # sharing a real account. Only the hash is stored -- same
    # generate/hash/verify shape as the refresh-token secret in
    # core/security.py -- so a leaked database dump alone can't be used to
    # download a still-live share link. None/None means no active link;
    # issuing a new one overwrites these (one live link per job at a time,
    # see export_job_service.create_share_link).
    share_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    share_token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    share_created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Set on the first successful download (see export_job_service.record_download).
    # None means "never downloaded" -- what the undownloaded-export monitor
    # (app/services/undownloaded_export_monitor.py) and AFTER_DOWNLOAD
    # cleanup mode (ExportSettings) both key off. A share-link download
    # counts as a download the same way an authenticated one does.
    downloaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
