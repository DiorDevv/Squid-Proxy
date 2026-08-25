"""Background job that watches for a Telegram pairing code being sent to
the bot (see app/services/telegram_link_service.py for issuing/redeeming
codes, app/models/telegram_link_code.py for the table).

Long-polls Telegram's getUpdates endpoint (the `timeout` param below is
Telegram's own long-poll wait, not this job's IntervalJob interval) --
near-real-time without a public webhook URL/TLS cert, matching this
codebase's existing "background IntervalJob" style rather than adding a
new inbound HTTP surface.
"""

import logging
import re

import httpx

from app.core.config import get_settings
from app.models.db import AsyncSessionLocal
from app.models.telegram_link_code import TelegramLinkTarget
from app.services import telegram_alerting, telegram_link_service
from app.services.interval_job import IntervalJob

logger = logging.getLogger(__name__)

# How long Telegram holds a getUpdates request open waiting for a new
# message before responding empty -- not this job's own interval_seconds
# (see run(), below), which just controls the gap between one long-poll
# request ending and the next starting.
_LONG_POLL_TIMEOUT_SECONDS = 25
_HTTP_TIMEOUT_SECONDS = _LONG_POLL_TIMEOUT_SECONDS + 10

_CODE_PATTERN = re.compile(r"\d{6}")

_PROMPT_TEXT = "Assalomu alaykum! Saytda ko'rsatilgan 6 xonali kodni shu yerga yuboring."
_SUCCESS_BRANCH_TEXT = (
    '✅ Ulanish muvaffaqiyatli! Bu chat endi "{branch}" filialining ogohlantirishlarini oladi.'
)
_SUCCESS_SUPER_ADMIN_TEXT = (
    "✅ Ulanish muvaffaqiyatli! Bu chat endi barcha filiallarning ogohlantirishlarini oladi "
    "(bosh admin sifatida)."
)
_INVALID_CODE_TEXT = "❌ Kod noto'g'ri yoki muddati o'tgan. Saytda yangi kod so'rang."


async def _get_updates(bot_token: str, offset: int | None) -> list[dict]:
    params: dict[str, int] = {"timeout": _LONG_POLL_TIMEOUT_SECONDS}
    if offset is not None:
        params["offset"] = offset
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates", params=params
        )
        response.raise_for_status()
        return response.json()["result"]


class TelegramLinkPollerJob(IntervalJob):
    job_name = "telegram-link-poller"
    failure_source_tag = "telegram_link_poller"
    failure_log_message = "Telegram link poller failed; will retry next interval"

    def __init__(self, interval_seconds: int = 1) -> None:
        super().__init__(interval_seconds)
        # In-memory only, unlike log_tailer.py's disk-persisted read
        # position -- reprocessing the last unconfirmed batch after a
        # restart is safe here (consume_code is idempotent: an
        # already-consumed code just no-ops back to "invalid"), so the
        # extra durability isn't worth the complexity for this feature.
        self._offset: int | None = None

    async def run(self) -> None:
        settings = get_settings()
        if not settings.TELEGRAM_BOT_TOKEN:
            return

        updates = await _get_updates(settings.TELEGRAM_BOT_TOKEN, self._offset)
        for update in updates:
            self._offset = update["update_id"] + 1
            message = update.get("message")
            if message and "text" in message:
                await self._handle_message(settings.TELEGRAM_BOT_TOKEN, message)

    async def _handle_message(self, bot_token: str, message: dict) -> None:
        chat_id = str(message["chat"]["id"])
        text = str(message.get("text", "")).strip()

        if text == "/start":
            await telegram_alerting.send_message(bot_token, chat_id, _PROMPT_TEXT)
            return

        if text.startswith("/start "):
            text = text[len("/start ") :].strip()

        if not _CODE_PATTERN.fullmatch(text):
            return

        async with AsyncSessionLocal() as session:
            row = await telegram_link_service.consume_code(session, text, chat_id)

        if row is None:
            await telegram_alerting.send_message(bot_token, chat_id, _INVALID_CODE_TEXT)
            return

        reply = (
            _SUCCESS_BRANCH_TEXT.format(branch=row.branch)
            if row.target == TelegramLinkTarget.BRANCH
            else _SUCCESS_SUPER_ADMIN_TEXT
        )
        await telegram_alerting.send_message(bot_token, chat_id, reply)
