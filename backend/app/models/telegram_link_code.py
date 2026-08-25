import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.types import UTCDateTime


class TelegramLinkTarget(str, enum.Enum):
    # A single branch's AlertSettings.telegram_chat_id.
    BRANCH = "branch"
    # The global TelegramGlobalSettings.super_admin_chat_id (see
    # app/models/telegram_global_settings.py) -- every branch's alerts.
    SUPER_ADMIN = "super_admin"


class TelegramLinkCode(Base):
    """A short-lived pairing code shown in the dashboard and redeemed by
    sending it to the bot in Telegram (see app/services/telegram_link_service.py
    for issuing/consuming, app/services/telegram_link_poller.py for the
    background job that watches for it arriving in Telegram).

    Replaces asking an admin to manually discover and paste a raw numeric
    chat id: instead they click "Connect", get a 6-digit code, and send it
    to the bot -- the bot (via the poller) resolves the sender's chat id
    for them.
    """

    __tablename__ = "telegram_link_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(6), index=True)
    target: Mapped[TelegramLinkTarget] = mapped_column(Enum(TelegramLinkTarget))
    # Set iff target == BRANCH; None for a SUPER_ADMIN code.
    branch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Both None until a matching Telegram message redeems this code (see
    # telegram_link_service.consume_code). consumed_chat_id is what actually
    # got written to AlertSettings/TelegramGlobalSettings -- kept here too
    # so the status endpoint can report it without a second lookup.
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    consumed_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
