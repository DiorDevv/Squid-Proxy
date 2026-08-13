from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import DEFAULT_BRANCH
from app.schemas.alerts import AlertSettingsOut, UpdateAlertSettingsRequest
from app.services import alert_settings_service

router = APIRouter(
    prefix="/api/alert-settings", tags=["alert-settings"], dependencies=[Depends(require_admin)]
)


async def _scoped_branch(
    branch: str = Query(default=DEFAULT_BRANCH),
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    """Same substitution/rejection contract as api.deps.resolve_branch, but
    with DEFAULT_BRANCH (not None/"all") as the concrete fallback these
    single-branch settings need: a branch-scoped admin is pinned to their
    own branch, silently if they didn't ask for a specific one, 403 if they
    explicitly asked for a different one -- previously unchecked, letting
    any branch-scoped admin read or overwrite another branch's alert
    thresholds."""
    if current_user.branch is not None and branch != DEFAULT_BRANCH and branch != current_user.branch:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this branch."
        )
    return current_user.branch or branch


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
    branch: str = Depends(_scoped_branch), db: AsyncSession = Depends(get_db)
) -> AlertSettingsOut:
    row = await alert_settings_service.get_settings_row(db, branch)
    return _to_out(row)


@router.put("", response_model=AlertSettingsOut)
async def update_alert_settings(
    body: UpdateAlertSettingsRequest,
    branch: str = Depends(_scoped_branch),
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
