"""The super-admin's global Telegram chat id (see
app/models/telegram_global_settings.py). Consumed by
app/services/telegram_alerting.py; written either by a manual PUT (not
currently exposed -- see telegram_link_service.consume_code, the only
writer today) or by redeeming a pairing code.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction
from app.models.telegram_global_settings import TelegramGlobalSettings
from app.services import audit_service

SETTINGS_ROW_ID = 1


async def get_settings_row(session: AsyncSession) -> TelegramGlobalSettings:
    """Read-only: returns the persisted singleton row, or an unsaved,
    in-memory default (super_admin_chat_id=None) if it's never been
    configured yet -- matches export_settings_service.get_settings_row's
    "no row inserted just to be read from" reasoning."""
    row = await session.get(TelegramGlobalSettings, SETTINGS_ROW_ID)
    if row is None:
        row = TelegramGlobalSettings(
            id=SETTINGS_ROW_ID, super_admin_chat_id=None, updated_at=datetime.now(UTC)
        )
    return row


async def set_super_admin_chat_id(
    session: AsyncSession, chat_id: str, actor_user_id: str
) -> TelegramGlobalSettings:
    """Does not commit -- the only caller (telegram_link_service.consume_code)
    commits once alongside its own TelegramLinkCode row update, so a code
    is never marked consumed without the chat id it resolved to actually
    being saved, or vice versa."""
    row = await session.get(TelegramGlobalSettings, SETTINGS_ROW_ID)
    if row is None:
        row = TelegramGlobalSettings(id=SETTINGS_ROW_ID)
        session.add(row)

    row.super_admin_chat_id = chat_id
    await audit_service.record(
        session,
        action=AuditAction.TELEGRAM_LINKED,
        actor_user_id=actor_user_id,
        detail="Super-admin Telegram chat linked via pairing code",
    )
    return row
