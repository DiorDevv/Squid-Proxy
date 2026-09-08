"""Assembles GET /api/system-health. Everything here is cheap: a handful of
metadata queries, one statvfs, in-memory job/tailer state, and two small
JSON files. No scan of raw_events beyond COUNT with an indexed predicate.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.health import build_health_snapshot
from app.core.config import get_settings
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.models.system_event import SystemEvent
from app.schemas.system_health import (
    BackgroundJob,
    BackupStatus,
    BranchIngest,
    DatabaseHealth,
    DiskHealth,
    IngestionHealth,
    OffsiteStatus,
    SystemEventOut,
    SystemHealthResponse,
    TableSize,
)

logger = logging.getLogger(__name__)

_PG_TABLE_SIZES = text(
    "SELECT relname, pg_total_relation_size(relid) AS bytes "
    "FROM pg_catalog.pg_statio_user_tables ORDER BY bytes DESC LIMIT 10"
)
_PG_DB_SIZE = text("SELECT pg_database_size(current_database())")
_SQLITE_DB_SIZE = text("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")


async def _database_health(session: AsyncSession) -> DatabaseHealth:
    dialect = session.bind.dialect.name if session.bind else "unknown"
    total_bytes: int | None = None
    tables: list[TableSize] = []
    try:
        if dialect == "postgresql":
            total_bytes = int((await session.execute(_PG_DB_SIZE)).scalar_one())
            rows = (await session.execute(_PG_TABLE_SIZES)).all()
            tables = [TableSize(name=r[0], bytes=int(r[1])) for r in rows]
        elif dialect == "sqlite":
            total_bytes = int((await session.execute(_SQLITE_DB_SIZE)).scalar_one())
    except Exception:
        logger.warning("Could not read database size", exc_info=True)

    oldest, newest = (
        await session.execute(select(func.min(RawEvent.timestamp), func.max(RawEvent.timestamp)))
    ).one()
    row_count = int((await session.execute(select(func.count()).select_from(RawEvent))).scalar_one())
    since_24h = datetime.now(UTC) - timedelta(hours=24)
    added_24h = int(
        (
            await session.execute(
                select(func.count()).select_from(RawEvent).where(RawEvent.timestamp >= since_24h)
            )
        ).scalar_one()
    )
    return DatabaseHealth(
        dialect=dialect,
        total_bytes=total_bytes,
        tables=tables,
        raw_events_oldest=oldest,
        raw_events_newest=newest,
        raw_events_row_count=row_count,
        raw_events_added_24h=added_24h,
    )


def _disk_health() -> DiskHealth | None:
    # The archives dir is bind-mounted from the host in the Docker
    # deployment (see docker-compose.yml), so statvfs here reports the host
    # filesystem that also holds the DB and backup volumes -- the disk that
    # actually matters. Falls back to the working directory.
    settings = get_settings()
    candidates = [settings.ARCHIVE_OUTPUT_DIR, settings.EXPORT_JOBS_DIR, "."]
    for cand in candidates:
        try:
            st = os.statvfs(cand)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if total <= 0:
            continue
        return DiskHealth(
            path=str(Path(cand).resolve()),
            total_bytes=total,
            free_bytes=free,
            used_pct=round((total - free) / total * 100, 1),
        )
    return None


async def _ingestion_health(app: FastAPI, session: AsyncSession) -> IngestionHealth:
    snap = build_health_snapshot(app)
    rows = (
        await session.execute(
            select(MinuteAggregate.branch, func.max(MinuteAggregate.bucket_ts)).group_by(
                MinuteAggregate.branch
            )
        )
    ).all()
    last_event: dict[str, datetime] = {r[0]: r[1] for r in rows if r[1] is not None}
    branches = [
        BranchIngest(
            branch=src["branch"],
            tailer_alive=src["alive"],
            lines_seen=src["lines_seen"],
            lines_parsed=src["lines_parsed"],
            parse_failure_rate=src["parse_failure_rate"],
            last_event_at=last_event.get(src["branch"]),
        )
        for src in snap["log_sources"]
    ]
    return IngestionHealth(
        branches=branches,
        aggregator_backlog_ratio=snap["aggregator_backlog_ratio"],
        aggregator_events_likely_lost=snap["aggregator_events_likely_lost"],
        unarchived_purge_branches=snap["unarchived_purge_branches"],
    )


def _background_jobs(app: FastAPI) -> list[BackgroundJob]:
    jobs = getattr(app.state, "background_jobs", {})
    out = [
        BackgroundJob(
            name=name,
            alive=job.is_alive,
            last_run_at=job.last_run_at,
            last_error=job.last_error,
            last_error_at=job.last_error_at,
            consecutive_failures=job.consecutive_failures,
        )
        for name, job in jobs.items()
    ]
    out.sort(key=lambda j: (j.alive, j.last_error is None, j.name))
    return out


def _read_status_file(name: str) -> dict | None:
    status_dir = get_settings().JOB_STATUS_DIR
    if not status_dir:
        return None
    try:
        return json.loads((Path(status_dir) / name).read_text())
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("Could not read status file %s", name, exc_info=True)
        return None


def _backup_status() -> BackupStatus | None:
    raw = _read_status_file("backup.json")
    if raw is None:
        return None
    status = BackupStatus(**{k: raw.get(k) for k in BackupStatus.model_fields if k != "stale"})
    stale_hours = get_settings().SYSTEM_HEALTH_BACKUP_STALE_HOURS
    if status.last_success_at is None:
        status.stale = True
    else:
        last = status.last_success_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        status.stale = datetime.now(UTC) - last > timedelta(hours=stale_hours)
    return status


def _offsite_status() -> OffsiteStatus | None:
    raw = _read_status_file("offsite.json")
    if raw is None:
        return None
    return OffsiteStatus(**{k: raw.get(k) for k in OffsiteStatus.model_fields})


async def build(app: FastAPI, session: AsyncSession) -> SystemHealthResponse:
    events = (
        (await session.execute(select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(50)))
        .scalars()
        .all()
    )
    return SystemHealthResponse(
        generated_at=datetime.now(UTC),
        database=await _database_health(session),
        disk=_disk_health(),
        ingestion=await _ingestion_health(app, session),
        background_jobs=_background_jobs(app),
        backup=_backup_status(),
        offsite=_offsite_status(),
        recent_events=[
            SystemEventOut(
                created_at=e.created_at,
                source=e.source,
                severity=e.severity.value,
                message=e.message,
            )
            for e in events
        ],
    )
