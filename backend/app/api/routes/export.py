from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.export_job import ExportJobStatus
from app.schemas.common import EffectiveRange, resolve_range
from app.schemas.export import ExportJobOut
from app.services import export_job_service
from app.services.export_service import download_csv, download_json

router = APIRouter(prefix="/api", tags=["export"])


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


@router.get("/export", dependencies=[Depends(require_admin)])
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def export_events(
    request: Request,
    effective_range: EffectiveRange = Depends(resolve_range),
    format: ExportFormat = Query(default=ExportFormat.CSV),
    blocked_only: bool = Query(default=False),
    branch: str | None = Query(default=None),
) -> StreamingResponse:
    # Custom from_ts/to_ts ranges have no RangeParam label -- fall back to a
    # timestamp-based filename suffix so it's still descriptive.
    if effective_range.range:
        range_label = effective_range.range.value
    else:
        range_label = effective_range.until.date().isoformat()

    # Streamed (see export_service.download_csv/json), so a full range --
    # even one covering millions of rows, e.g. the 7d preset at real
    # traffic volumes -- downloads without being capped or built in memory
    # server-side.
    if format == ExportFormat.CSV:
        body = download_csv(effective_range.since, effective_range.until, blocked_only, branch)
        media_type = "text/csv"
        filename = f"squid-events-{range_label}.csv"
    else:
        body = download_json(effective_range.since, effective_range.until, blocked_only, branch)
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
    branch: str | None = Query(default=None),
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

    job = await export_job_service.create_job(
        db,
        effective_range.since,
        effective_range.until,
        format.value,
        blocked_only,
        branch,
        current_user.user_id,
    )
    export_job_service.start(job.id)
    return export_job_service.to_out(job)


@router.get("/export/jobs", dependencies=[Depends(require_admin)])
async def list_export_jobs(db: AsyncSession = Depends(get_db)) -> list[ExportJobOut]:
    jobs = await export_job_service.list_jobs(db)
    return [export_job_service.to_out(job) for job in jobs]


@router.get("/export/jobs/{job_id}", dependencies=[Depends(require_admin)])
async def get_export_job(job_id: str, db: AsyncSession = Depends(get_db)) -> ExportJobOut:
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    return export_job_service.to_out(job)


@router.post("/export/jobs/{job_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_export_job(job_id: str, db: AsyncSession = Depends(get_db)) -> ExportJobOut:
    """Requests cancellation of a still-in-flight job -- asynchronous (see
    export_job_service.request_cancellation), so the response still shows
    PENDING/RUNNING; poll GET /export/jobs/{id} for the CANCELLED status
    landing, the same way DONE/FAILED are already observed."""
    job = await export_job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")
    if job.status not in (ExportJobStatus.PENDING, ExportJobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export job already finished (status: {job.status.value}) -- nothing to cancel.",
        )
    export_job_service.request_cancellation(job_id)
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
        media_type="application/zip",
        filename=export_job_service.zip_filename(job),
        background=background_tasks,
    )
