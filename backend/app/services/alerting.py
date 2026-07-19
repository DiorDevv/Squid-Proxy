"""Best-effort webhook alerting for high-severity anomalies.

Fully optional and off by default: if ALERT_WEBHOOK_URL isn't configured,
`maybe_alert` is a no-op. A failed webhook delivery is logged and
swallowed -- alerting must never be able to take down the aggregator's
flush loop over a flaky endpoint.
"""

import logging

import httpx

from app.core.config import get_settings
from app.models.anomaly_event import AnomalyEvent, AnomalySeverity

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {
    AnomalySeverity.LOW: 0,
    AnomalySeverity.MEDIUM: 1,
    AnomalySeverity.HIGH: 2,
    AnomalySeverity.CRITICAL: 3,
}


async def maybe_alert(event: AnomalyEvent) -> None:
    settings = get_settings()
    if not settings.ALERT_WEBHOOK_URL:
        return

    min_severity = AnomalySeverity(settings.ALERT_MIN_SEVERITY)
    if _SEVERITY_RANK[event.severity] < _SEVERITY_RANK[min_severity]:
        return

    payload = {
        "title": event.title,
        "description": event.description,
        "severity": event.severity.value,
        "client_ip": event.client_ip,
        "domain": event.domain,
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
