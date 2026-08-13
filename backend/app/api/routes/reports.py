import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin, resolve_branch
from app.core.config import get_settings
from app.models.audit_log import AuditAction
from app.models.report_schedule_state import ReportScheduleState
from app.schemas.reports import ReportStatusOut, SendReportNowResponse
from app.services import audit_service
from app.services.report_scheduler import STATE_ROW_ID
from app.services.report_service import generate_and_send_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(require_admin)])


@router.get("/status", response_model=ReportStatusOut)
async def read_report_status(db: AsyncSession = Depends(get_db)) -> ReportStatusOut:
    settings = get_settings()
    row = (
        await db.execute(select(ReportScheduleState).where(ReportScheduleState.id == STATE_ROW_ID))
    ).scalar_one_or_none()
    return ReportStatusOut(
        schedule=settings.REPORT_SCHEDULE,
        recipients_configured=bool(settings.REPORT_RECIPIENTS),
        smtp_configured=bool(settings.SMTP_HOST and settings.SMTP_FROM_ADDRESS),
        last_sent_at=row.last_sent_at if row else None,
    )


@router.post("/send-now", response_model=SendReportNowResponse)
async def send_report_now(
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SendReportNowResponse:
    settings = get_settings()
    if not settings.REPORT_RECIPIENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "REPORT_RECIPIENTS is not configured.")
    if not settings.SMTP_HOST or not settings.SMTP_FROM_ADDRESS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "SMTP is not configured (SMTP_HOST / SMTP_FROM_ADDRESS)."
        )

    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    # No branch given: send one report per configured branch, same as the
    # scheduler (see report_scheduler.py), rather than a single combined one.
    branches = [branch] if branch else [source.branch for source in settings.effective_log_sources]
    try:
        for target_branch in branches:
            await generate_and_send_report(db, since, now, target_branch)
    except Exception as exc:
        # Full detail (which can include SMTP host/config internals) goes to
        # the log only -- same "log the real error, return a generic one"
        # contract as the app-wide handler in core/exceptions.py, which a
        # raised HTTPException here bypasses.
        logger.exception("Failed to send report on demand", extra={"branch": branch})
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Failed to send report. Check server logs for details."
        ) from exc

    await audit_service.record(
        db,
        action=AuditAction.REPORT_SENT_NOW,
        actor_user_id=current_user.user_id,
        detail=f"branch={branch or 'all'}",
    )
    await db.commit()

    return SendReportNowResponse(sent=True, since=since, until=now)
