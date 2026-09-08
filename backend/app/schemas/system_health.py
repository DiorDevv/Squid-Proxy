"""Response model for GET /api/system-health -- the operational snapshot
behind Settings -> System health. Assembled by
app/services/system_health_service.py from a handful of cheap DB queries,
os.statvfs, the same tailer/aggregator state /api/health reports, the
background jobs' own health counters, and the status JSONs the db-backup /
db-offsite jobs drop on a shared volume.
"""

from datetime import datetime

from pydantic import BaseModel


class TableSize(BaseModel):
    name: str
    bytes: int


class DatabaseHealth(BaseModel):
    dialect: str
    total_bytes: int | None
    tables: list[TableSize]
    raw_events_oldest: datetime | None
    raw_events_newest: datetime | None
    raw_events_row_count: int
    raw_events_added_24h: int


class DiskHealth(BaseModel):
    path: str
    total_bytes: int
    free_bytes: int
    used_pct: float


class BranchIngest(BaseModel):
    branch: str
    tailer_alive: bool
    lines_seen: int
    lines_parsed: int
    parse_failure_rate: float | None
    last_event_at: datetime | None


class IngestionHealth(BaseModel):
    branches: list[BranchIngest]
    aggregator_backlog_ratio: float
    aggregator_events_likely_lost: bool
    unarchived_purge_branches: list[str]


class BackgroundJob(BaseModel):
    name: str
    alive: bool
    last_run_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    consecutive_failures: int


class BackupStatus(BaseModel):
    updated_at: datetime | None = None
    ok: bool | None = None
    last_success_at: datetime | None = None
    last_dump: str | None = None
    last_dump_bytes: int | None = None
    consecutive_failures: int | None = None
    error: str | None = None
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
    # Set by the service, not the file: True if last_success_at is older
    # than SYSTEM_HEALTH_BACKUP_STALE_HOURS (or there's never been one).
    stale: bool | None = None


class OffsiteStatus(BaseModel):
    updated_at: datetime | None = None
    enabled: bool | None = None
    repo: str | None = None
    last_sync_at: datetime | None = None
    last_sync_ok: bool | None = None
    last_check_at: datetime | None = None
    last_check_ok: bool | None = None
    error: str | None = None


class SystemEventOut(BaseModel):
    created_at: datetime
    source: str
    severity: str
    message: str


class SystemHealthResponse(BaseModel):
    generated_at: datetime
    database: DatabaseHealth
    disk: DiskHealth | None
    ingestion: IngestionHealth
    background_jobs: list[BackgroundJob]
    backup: BackupStatus | None
    offsite: OffsiteStatus | None
    recent_events: list[SystemEventOut]
