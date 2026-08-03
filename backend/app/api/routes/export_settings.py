from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.models.export_settings import ExportSettings
from app.schemas.export_settings import ExportSettingsOut, UpdateExportSettingsRequest
from app.services import export_settings_service

router = APIRouter(
    prefix="/api/export-settings", tags=["export-settings"], dependencies=[Depends(require_admin)]
)


def _to_out(row: ExportSettings) -> ExportSettingsOut:
    return ExportSettingsOut(
        cleanup_mode=row.cleanup_mode,
        retention_hours=row.retention_hours,
        warn_undownloaded_after_hours=row.warn_undownloaded_after_hours,
        updated_at=row.updated_at,
    )


@router.get("", response_model=ExportSettingsOut)
async def read_export_settings(db: AsyncSession = Depends(get_db)) -> ExportSettingsOut:
    row = await export_settings_service.get_settings_row(db)
    return _to_out(row)


@router.put("", response_model=ExportSettingsOut)
async def update_export_settings(
    body: UpdateExportSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExportSettingsOut:
    row = await export_settings_service.update_settings(
        db,
        body.cleanup_mode,
        body.retention_hours,
        body.warn_undownloaded_after_hours,
        current_user.user_id,
    )
    return _to_out(row)
