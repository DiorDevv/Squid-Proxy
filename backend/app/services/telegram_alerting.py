"""Best-effort Telegram alerting for high-severity anomalies (see
app/services/alerting.py, which calls `notify` as one of its delivery
channels).

Fully optional and off by default: a no-op unless TELEGRAM_BOT_TOKEN is
set. Each anomaly can reach up to two chats -- TELEGRAM_SUPER_ADMIN_CHAT_ID
(every branch, for whoever needs the full picture) and the anomaly's own
branch's `AlertSettings.telegram_chat_id` (set per branch by that branch's
admin) -- deduplicated so a chat configured as both only gets one message.
A failed delivery is logged and swallowed, same contract as the webhook
channel.
"""

import html
import logging

import httpx

from app.core.config import get_settings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.models.db import AsyncSessionLocal
from app.services import alert_settings_service

logger = logging.getLogger(__name__)


def _format_message(event: AnomalyEvent) -> str:
    lines = [
        f"<b>{html.escape(event.title)}</b> ({event.severity.value.upper()})",
        html.escape(event.description),
    ]
    if event.client_ip:
        lines.append(f"Client: {html.escape(event.client_ip)}")
    if event.domain:
        lines.append(f"Domain: {html.escape(event.domain)}")
    lines.append(f"Branch: {html.escape(event.branch or '-')}")
    return "\n".join(lines)


async def _recipients(event: AnomalyEvent) -> set[str]:
    settings = get_settings()
    chat_ids: set[str] = set()
    if settings.TELEGRAM_SUPER_ADMIN_CHAT_ID:
        chat_ids.add(settings.TELEGRAM_SUPER_ADMIN_CHAT_ID)
    if event.branch:
        async with AsyncSessionLocal() as session:
            row = await alert_settings_service.get_settings_row(session, event.branch)
        if row.telegram_chat_id:
            chat_ids.add(row.telegram_chat_id)
    return chat_ids


async def send_message(bot_token: str, chat_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()


async def notify(event: AnomalyEvent) -> None:
    # Imported here (not at module scope) to avoid a circular import with
    # alerting.py, which imports this module to fan out to it.
    from app.services.alerting import meets_min_severity

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    min_severity = AnomalySeverity(settings.ALERT_MIN_SEVERITY)
    if not meets_min_severity(event.severity, min_severity):
        return

    chat_ids = await _recipients(event)
    if not chat_ids:
        return

    text = _format_message(event)
    for chat_id in chat_ids:
        try:
            await send_message(settings.TELEGRAM_BOT_TOKEN, chat_id, text)
        except Exception:
            logger.warning(
                "Failed to deliver Telegram alert",
                exc_info=True,
                extra={"title": event.title, "chat_id": chat_id},
            )
