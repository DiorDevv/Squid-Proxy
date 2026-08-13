from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin, resolve_branch
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.audit_log import AuditAction
from app.models.domain_category import DomainCategoryLabel
from app.models.export_job import ExportJob, ExportJobStatus
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.export import ExportJobOut, ExportShareLinkOut
from app.services import audit_service, export_job_service
from app.services.export_service import EXPORT_COLUMNS, download_csv, download_json

router = APIRouter(prefix="/api", tags=["export"])


def _authorize_job_access(job: ExportJob, current_user: CurrentUser) -> None:
    """A branch-scoped admin may only read/cancel/download/share a job
    scoped to their own branch. A job with no branch (created by an
    unrestricted admin, covers every branch) is out of reach too -- treated
    as 404 rather than 403 since, from a branch-scoped caller's point of
    view, a job it can't touch shouldn't confirm it exists."""
    if current_user.branch is not None and job.branch != current_user.branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


def _parse_columns(columns: str | None) -> list[str] | None:
    """`columns` arrives as a comma-separated query param (matching how
    ExportJob.columns is stored, see export_job_service.create_job) --
    `None`/empty means "every column", the long-standing default. Raises a
    clean 400 immediately on an unknown name rather than letting it surface
    later as a confusing error mid-stream or mid-job."""
    if columns is None or not columns.strip():
        return None
    requested = [c.strip() for c in columns.split(",") if c.strip()]
    unknown = [c for c in requested if c not in EXPORT_COLUMNS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown export column(s): {', '.join(unknown)}. "
                f"Valid columns: {', '.join(EXPORT_COLUMNS)}."
            ),
        )
    return requested


@router.get("/export", dependencies=[Depends(require_admin)])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def export_events(
    request: Request,
    effective_range: EffectiveRange = Depends(resolve_range),
    format: ExportFormat = Query(default=ExportFormat.CSV),
    blocked_only: bool = Query(default=False),
    branch: str | None = Depends(resolve_branch),
    client_ip: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    category: DomainCategoryLabel | None = Query(default=None),
    columns: str | None = Query(default=None, description="Comma-separated subset of the export columns."),
) -> StreamingResponse:
    # xlsx can't be produced as a genuine incremental stream (see
    # export_service.py's "XLSX, job-only" section) -- rejected here rather
    # than silently buffering a potentially unbounded range in memory to
    # fake the same StreamingResponse contract this endpoint otherwise
    # guarantees. POST /export/jobs (the background-job path) already
    # writes a complete file to disk before serving anything, so it has no
    # such constraint.
    if format == ExportFormat.XLSX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="xlsx is only available via POST /api/export/jobs (background export), not this "
            "synchronous endpoint. Create a job and download it once done.",
        )

    # Custom from_ts/to_ts ranges have no RangeParam label -- fall back to a
    # timestamp-based filename suffix so it's still descriptive.
    if effective_range.range:
        range_label = effective_range.range.value
    else:
        range_label = effective_range.until.date().isoformat()

    resolved_columns = _parse_columns(columns)

    # Streamed (see export_service.download_csv/json), so a full range --
    # even one covering millions of rows, e.g. the 7d preset at real
    # traffic volumes -- downloads without being capped or built in memory
    # server-side.
    if format == ExportFormat.CSV:
        body = download_csv(
            effective_range.since, effective_range.until, blocked_only, branch,
            client_ip=client_ip, domain=domain, category=category, columns=resolved_columns,
        )
        media_type = "text/csv"
        filename = f"squid-events-{range_label}.csv"
    else:
        body = download_json(
            effective_range.since, effective_range.until, blocked_only, branch,
            client_ip=client_ip, domain=domain, category=category, columns=resolved_columns,
        )
        media_type = "application/json"
        filename = f"squid-events-{range_label}.json"

    return StreamingResponse(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/jobs", dependencies=[Depends(require_admin)], status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def create_export_job(
    request: Request,
    effective_range: EffectiveRange = Depends(resolve_range),
    format: ExportFormat = Query(default=ExportFormat.CSV),
    blocked_only: bool = Query(default=False),
    branch: str | None = Depends(resolve_branch),
    client_ip: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    category: DomainCategoryLabel | None = Query(default=None),
    columns: str | None = Query(default=None, description="Comma-separated subset of the export columns."),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportJobOut:
    """Same range/format/filters as GET /export, but runs in the
    background: returns a PENDING job immediately rather than holding the
    connection open until the export finishes. Poll GET
    /export/jobs/{id}, then GET /export/jobs/{id}/download once DONE."""
    active_count = await export_job_service.count_active_jobs(db)
    if active_count >= get_settings().EXPORT_JOB_MAX_CONCURRENT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many exports are already running. Wait for one to finish and try again.",
        )

    resolved_columns = _parse_columns(columns)

    job = await export_job_service.create_job(
        db,
        effective_range.since,
        effective_range.until,
        format.value,
        blocked_only,
        branch,
        current_user.user_id,
        client_ip=client_ip,
        domain=domain,
        category=category.value if category is not None else None,
        columns=resolved_columns,
    )
    export_job_service.start(job.id)
    return export_job_service.to_out(job)


@router.get("/export/jobs", dependencies=[Depends(require_admin)])
async def list_export_jobs(
    branch: str | None = Depends(resolve_branch), db: AsyncSession = Depends(get_db)
) -> list[ExportJobOut]:
    jobs = await export_job_service.list_jobs(db, branch=branch)
    return [export_job_service.to_out(job) for job in jobs]


@router.get("/export/jobs/{job_id}", dependencies=[Depends(require_admin)])
async def get_export_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportJobOut:
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    _authorize_job_access(job, current_user)
    return export_job_service.to_out(job)


@router.post("/export/jobs/{job_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_export_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportJobOut:
    """Requests cancellation of a still-in-flight job -- asynchronous (see
    export_job_service.request_cancellation), so the response still shows
    PENDING/RUNNING; poll GET /export/jobs/{id} for the CANCELLED status
    landing, the same way DONE/FAILED are already observed."""
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    _authorize_job_access(job, current_user)
    if job.status not in (ExportJobStatus.PENDING, ExportJobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export job already finished (status: {job.status.value}) -- nothing to cancel.",
        )
    export_job_service.request_cancellation(job_id)
    # request_cancellation() is a sync, non-session in-memory operation
    # (unlike every other audited export action, which audits inside its
    # own service function alongside a DB write) -- so this audits directly
    # here instead.
    await audit_service.record(
        db, action=AuditAction.EXPORT_CANCELLED, actor_user_id=current_user.user_id, detail=f"job_id={job_id}"
    )
    await db.commit()
    return export_job_service.to_out(job)


@router.get("/export/jobs/{job_id}/download", dependencies=[Depends(require_admin)])
async def download_export_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    _authorize_job_access(job, current_user)
    if job.status != ExportJobStatus.DONE or not job.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export job is not ready yet (status: {job.status.value}).",
        )

    await export_job_service.record_download(db, job, current_user.user_id)

    # Runs after the file has been fully streamed to the client -- never
    # races the FileResponse below. No-ops unless ExportSettings.cleanup_mode
    # is AFTER_DOWNLOAD (see export_job_service.delete_file_if_after_download_mode).
    background_tasks.add_task(export_job_service.delete_file_if_after_download_mode, job_id)

    return FileResponse(
        job.file_path,
        media_type=_media_type_for(job.format),
        filename=export_job_service.result_filename(job),
        background=background_tasks,
    )


def _media_type_for(format: str) -> str:
    if format == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/zip"


@router.post("/export/jobs/{job_id}/share", dependencies=[Depends(require_admin)])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def share_export_job(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportShareLinkOut:
    """Issues a time-limited (EXPORT_SHARE_LINK_TTL_HOURS) link that
    downloads this job's result without a dashboard login -- see GET
    /export/jobs/{id}/shared-download. Only one active link per job; calling
    this again replaces whichever one existed before (see
    export_job_service.create_share_link)."""
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    _authorize_job_access(job, current_user)
    if job.status != ExportJobStatus.DONE or not job.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export job is not ready yet (status: {job.status.value}).",
        )
    return await export_job_service.create_share_link(db, job, current_user.user_id)


@router.post("/export/jobs/{job_id}/share/revoke", dependencies=[Depends(require_admin)])
async def revoke_export_job_share(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportJobOut:
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    _authorize_job_access(job, current_user)
    await export_job_service.revoke_share_link(db, job, current_user.user_id)
    return export_job_service.to_out(job)


@router.get("/export/jobs/{job_id}/shared-download")
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def download_shared_export_job(
    request: Request,
    job_id: str,
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Deliberately outside `require_admin`/`get_current_user` -- the whole
    point of a share link is downloading without a dashboard account. The
    token itself (256 bits, only its hash ever stored, see
    export_job_service.verify_share_token) is the only credential; the rate
    limit above is defense-in-depth against guessing it, not the primary
    protection."""
    job = await export_job_service.verify_share_token(db, job_id, token)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid, expired, or revoked share link."
        )
    if job.status != ExportJobStatus.DONE or not job.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export job is not ready yet (status: {job.status.value}).",
        )

    # actor_user_id is whoever *issued* the link, not whoever's browser is
    # sitting here right now -- see record_download's via_share_link
    # docstring for why that's the right attribution for this audit entry.
    await export_job_service.record_download(
        db, job, job.share_created_by or "unknown", via_share_link=True
    )

    background_tasks.add_task(export_job_service.delete_file_if_after_download_mode, job_id)

    return FileResponse(
        job.file_path,
        media_type=_media_type_for(job.format),
        filename=export_job_service.result_filename(job),
        background=background_tasks,
    )
