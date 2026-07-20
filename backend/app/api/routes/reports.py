from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.config import get_settings
from app.models.report_schedule_state import ReportScheduleState
from app.schemas.reports import ReportStatusOut, SendReportNowResponse
from app.services.report_scheduler import STATE_ROW_ID
from app.services.report_service import generate_and_send_report

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
    branch: str | None = Query(default=None), db: AsyncSession = Depends(get_db)
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
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Failed to send report: {exc}") from exc

    return SendReportNowResponse(sent=True, since=since, until=now)
