from datetime import UTC, datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class TelegramGlobalSettings(Base):
    """The super-admin's Telegram chat id -- every branch's alerts go here
    in addition to that branch's own AlertSettings.telegram_chat_id (see
    app/services/telegram_alerting.py). Singleton row (id always 1), same
    reasoning as ExportSettings: one global, admin-editable value, not a
    per-branch concern.

    TELEGRAM_SUPER_ADMIN_CHAT_ID (app/core/config.py) is still read as a
    fallback when this row's super_admin_chat_id is unset -- an existing
    deployment's env-configured value keeps working without needing to be
    re-linked through the dashboard.
    """

    __tablename__ = "telegram_global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    super_admin_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
