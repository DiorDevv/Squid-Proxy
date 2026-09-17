from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.models.retention_settings import RetentionSettings
from app.schemas.retention_settings import RetentionSettingsOut, UpdateRetentionSettingsRequest
from app.services import retention_settings_service

router = APIRouter(
    prefix="/api/retention-settings", tags=["retention-settings"], dependencies=[Depends(require_admin)]
)


def _to_out(row: RetentionSettings) -> RetentionSettingsOut:
    return RetentionSettingsOut(
        raw_events_days=row.raw_events_days,
        halt_purge_if_archive_lag_days=row.halt_purge_if_archive_lag_days,
        updated_at=row.updated_at,
    )


@router.get("", response_model=RetentionSettingsOut)
async def read_retention_settings(db: AsyncSession = Depends(get_db)) -> RetentionSettingsOut:
    return _to_out(await retention_settings_service.get_settings_row(db))


@router.put("", response_model=RetentionSettingsOut)
async def update_retention_settings(
    body: UpdateRetentionSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RetentionSettingsOut:
    """Lowering `raw_events_days` permanently deletes the now-out-of-window
    rows on the next retention purge -- the frontend confirms before
    sending. Every change is audited (RETENTION_SETTINGS_UPDATED)."""
    row = await retention_settings_service.update_settings(
        db,
        body.raw_events_days,
        body.halt_purge_if_archive_lag_days,
        current_user.user_id,
    )
    return _to_out(row)
