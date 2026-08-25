"""Best-effort alert delivery for high-severity anomalies: a generic
webhook (this module) and, alongside it, Telegram (app/services/
telegram_alerting.py). `maybe_alert` is the single chokepoint every
anomaly-producing call site (aggregator.py and the interval monitor jobs)
awaits per persisted row, so it fans out to every configured channel
itself rather than each call site awaiting each channel separately.

Both channels are fully optional and off by default: if a channel isn't
configured, its delivery is a no-op. A failed delivery is logged and
swallowed -- alerting must never be able to take down the aggregator's
flush loop over a flaky endpoint.
"""

import logging

import httpx

from app.core.config import get_settings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity
from app.services import telegram_alerting

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {
    AnomalySeverity.LOW: 0,
    AnomalySeverity.MEDIUM: 1,
    AnomalySeverity.HIGH: 2,
    AnomalySeverity.CRITICAL: 3,
}


def meets_min_severity(severity: AnomalySeverity, min_severity: AnomalySeverity) -> bool:
    return _SEVERITY_RANK[severity] >= _SEVERITY_RANK[min_severity]


async def maybe_alert(event: AnomalyEvent) -> None:
    await _maybe_webhook_alert(event)
    await telegram_alerting.notify(event)


async def _maybe_webhook_alert(event: AnomalyEvent) -> None:
    settings = get_settings()
    if not settings.ALERT_WEBHOOK_URL:
        return

    min_severity = AnomalySeverity(settings.ALERT_MIN_SEVERITY)
    if not meets_min_severity(event.severity, min_severity):
        return

    # "text" makes this deliverable to a real Slack incoming webhook as-is --
    # Slack's API 400s (and this whole POST fails, per the try/except below)
    # on a payload with neither "text" nor "blocks". Slack renders "text" and
    # ignores the other keys, so non-Slack consumers still get the full
    # structured payload alongside it.
    text_lines = [f"*{event.title}* ({event.severity.value.upper()})", event.description]
    if event.client_ip:
        text_lines.append(f"Client: {event.client_ip}")
    if event.domain:
        text_lines.append(f"Domain: {event.domain}")
    text_lines.append(f"Branch: {event.branch}")

    payload = {
        "text": "\n".join(text_lines),
        "title": event.title,
        "description": event.description,
        "severity": event.severity.value,
        "client_ip": event.client_ip,
        "domain": event.domain,
        "branch": event.branch,
        "generated_at": event.generated_at.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.ALERT_WEBHOOK_URL, json=payload)
            response.raise_for_status()
    except Exception:
        logger.warning(
            "Failed to deliver alert webhook", exc_info=True, extra={"title": event.title}
        )
