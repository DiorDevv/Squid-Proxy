from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import DEFAULT_BRANCH
from app.schemas.alerts import AlertSettingsOut, UpdateAlertSettingsRequest
from app.services import alert_settings_service

router = APIRouter(
    prefix="/api/alert-settings", tags=["alert-settings"], dependencies=[Depends(require_admin)]
)


def _to_out(row) -> AlertSettingsOut:
    return AlertSettingsOut(
        branch=row.branch,
        sensitive_categories=sorted(
            alert_settings_service.parse_sensitive_categories(row.sensitive_categories), key=lambda c: c.value
        ),
        non_work_minutes_threshold=row.non_work_minutes_threshold,
        client_daily_byte_quota_bytes=row.client_daily_byte_quota_bytes,
        uncategorized_domain_request_threshold=row.uncategorized_domain_request_threshold,
        updated_at=row.updated_at,
    )


@router.get("", response_model=AlertSettingsOut)
async def read_alert_settings(
    branch: str = Query(default=DEFAULT_BRANCH), db: AsyncSession = Depends(get_db)
) -> AlertSettingsOut:
    row = await alert_settings_service.get_settings_row(db, branch)
    return _to_out(row)


@router.put("", response_model=AlertSettingsOut)
async def update_alert_settings(
    body: UpdateAlertSettingsRequest,
    branch: str = Query(default=DEFAULT_BRANCH),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AlertSettingsOut:
    row = await alert_settings_service.update_settings(
        db,
        sensitive_categories=body.sensitive_categories,
        non_work_minutes_threshold=body.non_work_minutes_threshold,
        client_daily_byte_quota_bytes=body.client_daily_byte_quota_bytes,
        actor_user_id=current_user.user_id,
        uncategorized_domain_request_threshold=body.uncategorized_domain_request_threshold,
        branch=branch,
    )
    return _to_out(row)
