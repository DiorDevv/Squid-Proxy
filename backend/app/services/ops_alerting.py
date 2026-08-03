"""Best-effort webhook alerting for operator-facing infra failures (the log
tailer dying, a background job erroring out, a backup failing) -- distinct
from app/services/alerting.py, which is specifically traffic-anomaly
alerting keyed off AnomalyEvent (client_ip/domain/severity fields that
don't apply here). Same delivery shape (httpx, 5s timeout,
catch-and-log-swallow): a failed webhook delivery must never be able to
take down the caller (a background job's error-handling wrapper, or a
backup script's failure path) over a flaky endpoint.

Fully optional: a no-op unless OPS_ALERT_WEBHOOK_URL (or, as a fallback,
ALERT_WEBHOOK_URL) is configured. No severity gate like alerting.py's
ALERT_MIN_SEVERITY -- every call site here already only fires on a real
failure, not a routine event, so there's nothing to threshold.
"""

import logging
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def notify_operator_failure(source: str, message: str, *, exc_info: bool = True) -> None:
    """source: a short stable tag ("log_tailer:filiallar", "retention",
    "backup", ...) identifying what broke, so whoever receives the alert
    can triage without reading logs first."""
    settings = get_settings()
    webhook_url = settings.OPS_ALERT_WEBHOOK_URL or settings.ALERT_WEBHOOK_URL
    if not webhook_url:
        return

    payload = {
        # Makes this deliverable to a real Slack incoming webhook as-is --
        # see app/services/alerting.py's payload for the same reasoning.
        "text": f"*Squid Watch operator alert: {source}*\n{message}",
        "title": f"Squid Watch operator alert: {source}",
        "description": message,
        "severity": "high",
        "source": source,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
    except Exception:
        logger.warning(
            "Failed to deliver operator-alert webhook",
            exc_info=exc_info,
            extra={"source": source},
        )
