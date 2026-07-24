"""Runs GET /api/export's CSV/JSON export as a background job instead of
tying up the requesting connection for as long as the range takes.

A job is created (PENDING) and handed to run_job() as a fire-and-forget
asyncio task (see api/routes/export.py); run_job opens its own DB session
for the whole run (same reasoning as export_service.download_csv/json --
this outlives the request that created the job entirely, so a
request-scoped session would already be closed). While RUNNING, row_count
is updated roughly once a second as rows are actually written, so a client
polling GET /api/export/jobs/{id} sees live progress instead of a silent
wait -- a wide range at real traffic volumes can take minutes. A job can
also be cancelled mid-run (see request_cancellation / POST
/export/jobs/{id}/cancel).
"""

import asyncio
import logging
import time
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import db as db_module
from app.models.audit_log import AuditAction
from app.models.export_job import ExportJob, ExportJobStatus
from app.schemas.export import ExportJobOut
from app.services import audit_service
from app.services.export_service import stream_csv, stream_json

logger = logging.getLogger(__name__)

# asyncio only holds a weak reference to a task created via create_task --
# without keeping a strong reference somewhere, a task can be garbage
# collected mid-run. This set is that reference; each task removes itself
# on completion via the done callback below.
_background_tasks: set[asyncio.Task] = set()

# Cooperative cancellation: run_job checks this at the same checkpoints it
# already visits for progress commits (roughly once a second, or
# immediately if still PENDING), rather than using asyncio.Task.cancel().
# Hard-cancelling mid-await is risky here specifically because those awaits
# are DB queries (_iter_batches) -- cancelling one while the driver is
# mid-flight leaves no guarantee the session/connection is left in a usable
# state. Checking a flag between whole batches never interrupts an
# in-flight query at all.
_cancel_requested: set[str] = set()


class _JobCancelled(Exception):
    pass


def request_cancellation(job_id: str) -> None:
    """Called from POST /export/jobs/{id}/cancel. Asynchronous by nature --
    the caller sees the PENDING/RUNNING status it already had; the status
    only actually flips to CANCELLED once run_job's loop next checks this
    (within about a second), the same way a client already has to poll to
    see DONE/FAILED land."""
    _cancel_requested.add(job_id)


def start(job_id: str) -> None:
    """Fires run_job(job_id) as a detached background task -- called right
    after create_job() commits, so the request returns immediately with a
    PENDING job instead of waiting for the export to finish."""
    task = asyncio.create_task(run_job(job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def to_out(job: ExportJob) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        status=job.status,
        format=job.format,
        since=job.since,
        until=job.until,
        blocked_only=job.blocked_only,
        branch=job.branch,
        row_count=job.row_count,
        file_size_bytes=job.file_size_bytes,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


async def create_job(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    format: str,
    blocked_only: bool,
    branch: str | None,
    actor_user_id: str,
) -> ExportJob:
    job = ExportJob(
        id=str(uuid.uuid4()),
        status=ExportJobStatus.PENDING,
        format=format,
        since=since,
        until=until,
        blocked_only=blocked_only,
        branch=branch,
        created_at=datetime.now(UTC),
    )
    session.add(job)
    # Exporting raw traffic data (client IPs, usernames, URLs) is a
    # security-relevant action in the same way user-management changes are
    # (see audit_service.record's other callers in user_service.py) -- an
    # admin needs to be able to answer "who pulled what data, and when."
    # No target_user_id/target_email: this action isn't about another
    # account, so both stay unset (see AuditLogEntry's docstring). job_id is
    # included so this entry can be correlated with the EXPORT_DOWNLOADED
    # one record_download logs below -- on this shared job list any admin
    # can download a job another admin queued, so the two aren't always the
    # same actor.
    detail = (
        f"job_id={job.id}, format={format}, since={since.isoformat()}, "
        f"until={until.isoformat()}, blocked_only={blocked_only}"
    )
    if branch:
        detail += f", branch={branch}"
    await audit_service.record(
        session,
        action=AuditAction.EXPORT_CREATED,
        actor_user_id=actor_user_id,
        detail=detail,
    )
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: str) -> ExportJob | None:
    return await session.get(ExportJob, job_id)


async def record_download(session: AsyncSession, job: ExportJob, actor_user_id: str) -> None:
    """Called from GET /export/jobs/{id}/download once a job is confirmed
    DONE and its file is about to be served. EXPORT_CREATED (see create_job)
    only proves someone *queued* an export; jobs are visible to every admin
    (list_jobs isn't scoped per-user), so whoever downloads a finished job
    isn't necessarily who created it -- this is the entry that proves the
    data actually left the system, and to whom."""
    detail = (
        f"job_id={job.id}, format={job.format}, since={job.since.isoformat()}, until={job.until.isoformat()}"
    )
    if job.branch:
        detail += f", branch={job.branch}"
    await audit_service.record(
        session,
        action=AuditAction.EXPORT_DOWNLOADED,
        actor_user_id=actor_user_id,
        detail=detail,
    )
    await session.commit()


async def list_jobs(session: AsyncSession, limit: int = 20) -> list[ExportJob]:
    query = select(ExportJob).order_by(ExportJob.created_at.desc()).limit(limit)
    return list((await session.execute(query)).scalars().all())


_ACTIVE_STATUSES = (ExportJobStatus.PENDING, ExportJobStatus.RUNNING)


async def count_active_jobs(session: AsyncSession) -> int:
    query = select(func.count()).select_from(ExportJob).where(ExportJob.status.in_(_ACTIVE_STATUSES))
    return (await session.execute(query)).scalar_one()


def _jobs_dir() -> Path:
    path = Path(get_settings().EXPORT_JOBS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _range_label(job: ExportJob) -> str:
    return (
        job.since.date().isoformat()
        if job.since.date() == job.until.date()
        else f"{job.since.date()}_{job.until.date()}"
    )


def inner_filename(job: ExportJob) -> str:
    """The CSV/JSON filename stored *inside* the zip -- what a user sees
    after extracting, matching what the plain (non-background) GET
    /api/export download would have been named."""
    return f"squid-events-{_range_label(job)}.{job.format}"


def zip_filename(job: ExportJob) -> str:
    """The filename download_export_job serves -- job.file_path itself is
    just f"{job_id}.zip" (see run_job), so callers need this to get a
    human-readable name for Content-Disposition."""
    return f"squid-events-{_range_label(job)}.zip"


async def reconcile_orphaned_jobs() -> int:
    """Marks any job still PENDING/RUNNING as of process start FAILED --
    called once from the lifespan on startup, before anything can create a
    new job.

    run_job() only ever moves a job out of PENDING/RUNNING from inside the
    asyncio task start() fired for it; that task lived in whatever process
    was running before this one, so a crash or restart mid-export leaves
    the row stuck "running" forever with nothing left to ever revisit it --
    and since count_active_jobs (see api/routes/export.py's
    EXPORT_JOB_MAX_CONCURRENT check) counts these as active, enough of them
    permanently wedges every future export behind a limit that can now
    never be satisfied.
    """
    async with db_module.AsyncSessionLocal() as session:
        stale_jobs = (
            (await session.execute(select(ExportJob).where(ExportJob.status.in_(_ACTIVE_STATUSES))))
            .scalars()
            .all()
        )
        for job in stale_jobs:
            # file_path is only ever set once run_job reaches DONE, so a job
            # caught here has none recorded -- but it follows the same
            # {job_id}.{format} / {job_id}.zip naming run_job would have
            # written to, so a best-effort unlink by those names still
            # catches whatever partial file was in progress, whichever
            # stage (raw write vs. zipping) the crash landed in.
            (_jobs_dir() / f"{job.id}.{job.format}").unlink(missing_ok=True)
            (_jobs_dir() / f"{job.id}.zip").unlink(missing_ok=True)
            job.status = ExportJobStatus.FAILED
            job.error_message = "Export was interrupted by a server restart."
            job.completed_at = datetime.now(UTC)
        await session.commit()
        return len(stale_jobs)


async def run_job(job_id: str) -> None:
    async with db_module.AsyncSessionLocal() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            logger.error("export job %s vanished before it could run", job_id)
            return

        if job_id in _cancel_requested:
            _cancel_requested.discard(job_id)
            job.status = ExportJobStatus.CANCELLED
            job.completed_at = datetime.now(UTC)
            await session.commit()
            return

        job.status = ExportJobStatus.RUNNING
        await session.commit()

        raw_path: Path | None = None
        zip_path: Path | None = None
        try:
            raw_path = _jobs_dir() / f"{job_id}.{job.format}"
            row_counter = [0]
            stream = (
                stream_csv(session, job.since, job.until, job.blocked_only, job.branch, row_counter)
                if job.format == "csv"
                else stream_json(session, job.since, job.until, job.blocked_only, job.branch, row_counter)
            )
            # A client polling GET /export/jobs/{id} while this is RUNNING
            # sees row_count update live -- the only feedback available for
            # a job that can take many minutes on a wide range at real
            # traffic volumes, otherwise it's just "running" with nothing to
            # show for potentially a very long time. Throttled to roughly
            # once a second (time-based, not per-batch) so a fast query
            # doing hundreds of small batches/sec doesn't turn a quick
            # export into hundreds of extra commits. Cancellation is
            # checked at the same checkpoint (see _JobCancelled above).
            last_progress_commit = time.monotonic()
            with raw_path.open("w", encoding="utf-8", newline="") as f:
                async for chunk in stream:
                    f.write(chunk)
                    if job_id in _cancel_requested:
                        raise _JobCancelled
                    now = time.monotonic()
                    if now - last_progress_commit >= 1.0:
                        job.row_count = row_counter[0]
                        await session.commit()
                        last_progress_commit = now

            # Zip the finished file rather than serving raw CSV/JSON --
            # that text compresses roughly 10-15x, so this both shrinks what
            # an admin has to download and what sits on disk until
            # purge_old_jobs reclaims it. Done after the raw file is
            # complete (not streamed straight into the zip) because
            # zipfile's writer needs to seek back to patch in the entry's
            # final size/CRC once it knows them.
            zip_path = _jobs_dir() / f"{job_id}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(raw_path, arcname=inner_filename(job))
            raw_path.unlink()

            job.status = ExportJobStatus.DONE
            job.file_path = str(zip_path)
            job.row_count = row_counter[0]
            job.file_size_bytes = zip_path.stat().st_size
            job.completed_at = datetime.now(UTC)
        except _JobCancelled:
            logger.info("export job %s cancelled", job_id)
            if raw_path is not None:
                raw_path.unlink(missing_ok=True)
            if zip_path is not None:
                zip_path.unlink(missing_ok=True)
            job.status = ExportJobStatus.CANCELLED
            job.row_count = row_counter[0]
            job.completed_at = datetime.now(UTC)
        except Exception as exc:
            logger.exception("export job %s failed", job_id)
            # Whatever stream_csv/stream_json managed to flush before the
            # error is a truncated, unusable file -- nothing ever points
            # job.file_path at it (download_export_job 409s without one), so
            # nothing else will ever clean it up.
            if raw_path is not None:
                raw_path.unlink(missing_ok=True)
            if zip_path is not None:
                zip_path.unlink(missing_ok=True)
            job.status = ExportJobStatus.FAILED
            job.error_message = str(exc)[:2000]
            job.completed_at = datetime.now(UTC)
        finally:
            _cancel_requested.discard(job_id)

        await session.commit()


async def purge_old_jobs(session: AsyncSession) -> int:
    """Deletes ExportJob rows (and their result files) older than
    EXPORT_JOB_RETENTION_HOURS -- called from RetentionJob.purge(). These
    are meant to be downloaded soon after they finish, not kept
    indefinitely; scripts/archive_weekly_export.py is the long-term archive
    path."""
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.EXPORT_JOB_RETENTION_HOURS)
    old_jobs = (
        (await session.execute(select(ExportJob).where(ExportJob.created_at < cutoff))).scalars().all()
    )
    for job in old_jobs:
        if job.file_path:
            Path(job.file_path).unlink(missing_ok=True)
        await session.delete(job)
    return len(old_jobs)
