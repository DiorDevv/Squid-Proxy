"""Admin-tunable data-retention policy (see app/models/retention_settings.py).
Consumed by app/services/retention.py (the purge itself), and read back by
GET /api/analytics/retention and GET /api/policy.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import AuditAction
from app.models.retention_settings import RetentionSettings
from app.services import audit_service

SETTINGS_ROW_ID = 1


async def get_settings_row(session: AsyncSession) -> RetentionSettings:
    """The persisted singleton, or an unsaved in-memory default seeded from
    the env var (RETENTION_DAYS_RAW_EVENTS) -- the same "no row inserted
    just to be read from" pattern as export_settings_service."""
    row = await session.get(RetentionSettings, SETTINGS_ROW_ID)
    if row is None:
        row = RetentionSettings(
            id=SETTINGS_ROW_ID,
            raw_events_days=get_settings().RETENTION_DAYS_RAW_EVENTS,
            halt_purge_if_archive_lag_days=None,
            updated_at=datetime.now(UTC),
        )
    return row


async def update_settings(
    session: AsyncSession,
    raw_events_days: int,
    halt_purge_if_archive_lag_days: int | None,
    actor_user_id: str,
) -> RetentionSettings:
    row = await session.get(RetentionSettings, SETTINGS_ROW_ID)
    old_raw_days = row.raw_events_days if row is not None else get_settings().RETENTION_DAYS_RAW_EVENTS
    if row is None:
        row = RetentionSettings(id=SETTINGS_ROW_ID)
        session.add(row)

    row.raw_events_days = raw_events_days
    row.halt_purge_if_archive_lag_days = halt_purge_if_archive_lag_days
    halt = "off" if halt_purge_if_archive_lag_days is None else f"{halt_purge_if_archive_lag_days}d"
    await audit_service.record(
        session,
        action=AuditAction.RETENTION_SETTINGS_UPDATED,
        actor_user_id=actor_user_id,
        detail=f"raw_events_days {old_raw_days} -> {raw_events_days}, halt_on_archive_lag={halt}",
    )
    await session.commit()
    await session.refresh(row)
    return row
