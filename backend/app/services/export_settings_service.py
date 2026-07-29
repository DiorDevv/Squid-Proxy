"""Admin-tunable export-job cleanup policy (see app/models/export_settings.py).
Consumed by app/services/export_job_service.py (purge_old_jobs, the
download route's post-download cleanup) and
app/services/undownloaded_export_monitor.py.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_settings import ExportCleanupMode, ExportSettings

SETTINGS_ROW_ID = 1
DEFAULT_RETENTION_HOURS = 48


async def get_settings_row(session: AsyncSession) -> ExportSettings:
    """Read-only: returns the persisted singleton row, or an unsaved,
    in-memory default if it's never been configured yet -- matches
    alert_settings_service.get_settings_row's "no row inserted just to be
    read from" reasoning."""
    row = await session.get(ExportSettings, SETTINGS_ROW_ID)
    if row is None:
        row = ExportSettings(
            id=SETTINGS_ROW_ID,
            cleanup_mode=ExportCleanupMode.TIME_BASED,
            retention_hours=DEFAULT_RETENTION_HOURS,
            warn_undownloaded_after_hours=None,
            updated_at=datetime.now(UTC),
        )
    return row


async def update_settings(
    session: AsyncSession,
    cleanup_mode: ExportCleanupMode,
    retention_hours: int,
    warn_undownloaded_after_hours: int | None,
) -> ExportSettings:
    row = await session.get(ExportSettings, SETTINGS_ROW_ID)
    if row is None:
        row = ExportSettings(id=SETTINGS_ROW_ID)
        session.add(row)

    row.cleanup_mode = cleanup_mode
    row.retention_hours = retention_hours
    row.warn_undownloaded_after_hours = warn_undownloaded_after_hours
    await session.commit()
    await session.refresh(row)
    return row
