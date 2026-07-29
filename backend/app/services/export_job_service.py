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
import hashlib
import logging
import secrets
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
from app.models.domain_category import DomainCategoryLabel
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.export_settings import ExportCleanupMode
from app.schemas.export import ExportJobOut, ExportShareLinkOut
from app.services import audit_service, export_settings_service
from app.services.export_service import (
    new_xlsx_workbook,
    resolve_category_domains,
    resolve_columns,
    stream_csv,
    stream_json,
    write_xlsx_rows,
)

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
        domain=job.domain,
        category=job.category,
        client_ip=job.client_ip,
        columns=job.columns.split(",") if job.columns else None,
        row_count=job.row_count,
        file_size_bytes=job.file_size_bytes,
        checksum_sha256=job.checksum_sha256,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        # Only whether a link exists, not the token itself -- the raw token
        # is only ever returned once, from create_share_link's own response
        # (see api/routes/export.py's POST /export/jobs/{id}/share), the
        # same "shown once, never re-derivable from stored state" contract
        # every secret in this codebase follows (passwords, refresh tokens).
        share_link_active=job.share_token_hash is not None
        and job.share_token_expires_at is not None
        and job.share_token_expires_at > datetime.now(UTC),
        share_link_expires_at=job.share_token_expires_at,
    )


async def create_job(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    format: str,
    blocked_only: bool,
    branch: str | None,
    actor_user_id: str,
    *,
    client_ip: str | None = None,
    domain: str | None = None,
    category: str | None = None,
    columns: list[str] | None = None,
) -> ExportJob:
    # Validated here (not left until run_job discovers a typo minutes into a
    # background run) -- resolve_columns raises ValueError on an unknown
    # name, which api/routes/export.py turns into a clean 400.
    resolved_columns = resolve_columns(columns)
    job = ExportJob(
        id=str(uuid.uuid4()),
        status=ExportJobStatus.PENDING,
        format=format,
        since=since,
        until=until,
        blocked_only=blocked_only,
        branch=branch,
        domain=domain,
        category=category,
        client_ip=client_ip,
        # None (every column, the long-standing default) is stored as None
        # rather than the fully-spelled-out list, so an old job predating
        # this feature and a fresh "give me everything" job both read back
        # the same way in to_out() above.
        columns=",".join(resolved_columns) if columns is not None else None,
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
    if domain:
        detail += f", domain={domain}"
    if category:
        detail += f", category={category}"
    if client_ip:
        detail += f", client_ip={client_ip}"
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


async def record_download(
    session: AsyncSession, job: ExportJob, actor_user_id: str, *, via_share_link: bool = False
) -> None:
    """Called from GET /export/jobs/{id}/download once a job is confirmed
    DONE and its file is about to be served. EXPORT_CREATED (see create_job)
    only proves someone *queued* an export; jobs are visible to every admin
    (list_jobs isn't scoped per-user), so whoever downloads a finished job
    isn't necessarily who created it -- this is the entry that proves the
    data actually left the system, and to whom.

    `via_share_link=True` (see the unauthenticated GET
    /export/jobs/{id}/shared-download route) means there's no real logged-in
    actor for this particular pull -- `actor_user_id` is the admin who
    *issued* the link (job.share_created_by), not whoever's browser actually
    used it, which the log line makes explicit rather than silently
    attributing an outside download to that admin as if they'd done it
    themselves."""
    detail = (
        f"job_id={job.id}, format={job.format}, since={job.since.isoformat()}, until={job.until.isoformat()}"
    )
    if job.branch:
        detail += f", branch={job.branch}"
    if via_share_link:
        detail += ", via=share_link"
    await audit_service.record(
        session,
        action=AuditAction.EXPORT_DOWNLOADED,
        actor_user_id=actor_user_id,
        detail=detail,
    )
    # Only the *first* download counts -- a job re-downloaded later (an
    # admin grabbing it again) shouldn't reset the undownloaded-export
    # monitor's clock or look "freshly downloaded" for AFTER_DOWNLOAD mode
    # (which will already have deleted the file after the first one).
    if job.downloaded_at is None:
        job.downloaded_at = datetime.now(UTC)
    await session.commit()


async def delete_file_if_after_download_mode(job_id: str) -> None:
    """Called as a FastAPI BackgroundTask from the download route -- i.e.
    only after the file has already been fully streamed to the client, so
    deleting it here can never race the response itself. Runs in its own
    session since BackgroundTasks execute after the request-scoped one
    (see api/deps.get_db) has already closed."""
    async with db_module.AsyncSessionLocal() as session:
        settings_row = await export_settings_service.get_settings_row(session)
        if settings_row.cleanup_mode != ExportCleanupMode.AFTER_DOWNLOAD:
            return

        job = await session.get(ExportJob, job_id)
        if job is None or job.file_path is None:
            return

        Path(job.file_path).unlink(missing_ok=True)
        job.file_path = None
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
    /api/export download would have been named. Not used for xlsx jobs,
    which have no outer zip (see run_job)."""
    return f"squid-events-{_range_label(job)}.{job.format}"


def result_filename(job: ExportJob) -> str:
    """The filename download_export_job (and the shared-download route)
    serve -- job.file_path itself is just f"{job_id}.zip"/f"{job_id}.xlsx"
    (see run_job), so callers need this to get a human-readable name for
    Content-Disposition. xlsx jobs skip the outer zip entirely (already a
    compressed container, and a second zip layer would only make an admin
    unzip twice for no size benefit), so this is the one place their
    extension actually differs from csv/json's .zip."""
    extension = "xlsx" if job.format == "xlsx" else "zip"
    return f"squid-events-{_range_label(job)}.{extension}"


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
        row_counter = [0]
        try:
            domain_in = (
                await resolve_category_domains(
                    session, job.since, job.until, DomainCategoryLabel(job.category), job.branch
                )
                if job.category is not None
                else None
            )
            resolved_columns = resolve_columns(job.columns.split(",") if job.columns else None)

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

            if job.format == "xlsx":
                # No outer zip step (see result_filename's docstring) --
                # raw_path *is* the finished file once workbook.save() runs.
                raw_path = _jobs_dir() / f"{job_id}.xlsx"
                workbook, worksheet = new_xlsx_workbook(resolved_columns)
                try:
                    async for _ in write_xlsx_rows(
                        worksheet,
                        session,
                        job.since,
                        job.until,
                        job.blocked_only,
                        job.branch,
                        job.client_ip,
                        job.domain,
                        domain_in,
                        resolved_columns,
                        row_counter,
                    ):
                        if job_id in _cancel_requested:
                            raise _JobCancelled
                        now = time.monotonic()
                        if now - last_progress_commit >= 1.0:
                            job.row_count = row_counter[0]
                            await session.commit()
                            last_progress_commit = now
                    workbook.save(str(raw_path))
                finally:
                    # Releases openpyxl's own internal temp file for this
                    # write-only workbook regardless of how the loop above
                    # exited -- save() was only reached on the success path.
                    workbook.close()
                result_path = raw_path
            else:
                raw_path = _jobs_dir() / f"{job_id}.{job.format}"
                stream_kwargs = {
                    "client_ip": job.client_ip,
                    "domain": job.domain,
                    "domain_in": domain_in,
                    "columns": resolved_columns,
                }
                stream_args = (session, job.since, job.until, job.blocked_only, job.branch, row_counter)
                stream = (
                    stream_csv(*stream_args, **stream_kwargs)
                    if job.format == "csv"
                    else stream_json(*stream_args, **stream_kwargs)
                )
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
                # that text compresses roughly 10-15x, so this both shrinks
                # what an admin has to download and what sits on disk until
                # purge_old_jobs reclaims it. Done after the raw file is
                # complete (not streamed straight into the zip) because
                # zipfile's writer needs to seek back to patch in the
                # entry's final size/CRC once it knows them.
                zip_path = _jobs_dir() / f"{job_id}.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(raw_path, arcname=inner_filename(job))
                raw_path.unlink()
                result_path = zip_path

            job.status = ExportJobStatus.DONE
            job.file_path = str(result_path)
            job.row_count = row_counter[0]
            job.file_size_bytes = result_path.stat().st_size
            job.checksum_sha256 = _sha256_file(result_path)
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
            # Whatever was flushed before the error is a truncated, unusable
            # file -- nothing ever points job.file_path at it
            # (download_export_job 409s without one), so nothing else will
            # ever clean it up.
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


def _sha256_file(path: Path) -> str:
    """Streamed (fixed-size chunks, never the whole file at once) so a
    multi-hundred-MB export doesn't get held entirely in memory a second
    time right after already being written -- same streaming discipline as
    everything else in this module."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def purge_old_jobs(session: AsyncSession) -> int:
    """Deletes ExportJob rows (and their result files) older than the
    admin-configured retention_hours (see app/models/export_settings.py) --
    called from RetentionJob.purge(). Only runs in TIME_BASED cleanup mode:
    in AFTER_DOWNLOAD mode, files are deleted individually right after each
    download instead (see delete_file_if_after_download_mode), and an
    undownloaded job is deliberately left alone here regardless of age --
    app/services/undownloaded_export_monitor.py is what surfaces that,
    not silent deletion. These rows are meant to be downloaded soon after
    they finish, not kept indefinitely; scripts/archive_weekly_export.py is
    the long-term archive path."""
    settings_row = await export_settings_service.get_settings_row(session)
    if settings_row.cleanup_mode != ExportCleanupMode.TIME_BASED:
        return 0

    cutoff = datetime.now(UTC) - timedelta(hours=settings_row.retention_hours)
    old_jobs = (
        (await session.execute(select(ExportJob).where(ExportJob.created_at < cutoff))).scalars().all()
    )
    for job in old_jobs:
        if job.file_path:
            Path(job.file_path).unlink(missing_ok=True)
        await session.delete(job)
    return len(old_jobs)


# --- Share links ---
#
# A time-limited, token-authenticated download for a finished job -- lets an
# admin hand a result to someone with no dashboard account (legal,
# compliance, an external auditor) without creating one just for a single
# file. Same generate/hash/verify shape as the refresh-token secret in
# core/security.py (raw value shown exactly once, only its SHA-256 stored),
# implemented locally rather than importing those refresh-token-named
# functions so this module's read of "what a share token is" can't drift
# just because auth's refresh-token format ever changes for unrelated
# reasons. One live link per job at a time: issuing a new one overwrites
# whatever was there, which is also how revocation works (see
# revoke_share_link) -- no separate list of past tokens to manage.


def _hash_share_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_share_link(session: AsyncSession, job: ExportJob, actor_user_id: str) -> ExportShareLinkOut:
    """Only ever callable for a DONE job with a file still on disk -- see
    api/routes/export.py's POST /export/jobs/{id}/share, which 409s before
    this is reached otherwise (a link to a file that doesn't exist yet, or
    never will, isn't useful to anyone)."""
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=get_settings().EXPORT_SHARE_LINK_TTL_HOURS)

    job.share_token_hash = _hash_share_token(raw_token)
    job.share_token_expires_at = expires_at
    job.share_created_by = actor_user_id

    await audit_service.record(
        session,
        action=AuditAction.EXPORT_SHARED,
        actor_user_id=actor_user_id,
        detail=f"job_id={job.id}, expires_at={expires_at.isoformat()}",
    )
    await session.commit()

    return ExportShareLinkOut(
        token=raw_token,
        expires_at=expires_at,
        download_url=f"/api/export/jobs/{job.id}/shared-download?token={raw_token}",
    )


async def revoke_share_link(session: AsyncSession, job: ExportJob) -> None:
    job.share_token_hash = None
    job.share_token_expires_at = None
    job.share_created_by = None
    await session.commit()


async def verify_share_token(session: AsyncSession, job_id: str, raw_token: str) -> ExportJob | None:
    """Called from the unauthenticated GET /export/jobs/{id}/shared-download
    route -- returns the job only if a link is currently active for it *and*
    the given token matches, so a wrong/stale/revoked token and "no link
    exists at all" both fail the exact same way (no signal to an attacker
    about which). `secrets.compare_digest` (not `==`) so comparing a guessed
    token against the stored hash can't leak timing information about how
    much of it matched."""
    job = await session.get(ExportJob, job_id)
    if job is None or job.share_token_hash is None or job.share_token_expires_at is None:
        return None
    if datetime.now(UTC) > job.share_token_expires_at:
        return None
    if not secrets.compare_digest(_hash_share_token(raw_token), job.share_token_hash):
        return None
    return job
