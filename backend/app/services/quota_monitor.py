"""Periodic check for clients exceeding a daily data-transfer quota (see
alert_settings_service.py for the admin-configurable
client_daily_byte_quota_bytes). Same start/stop/_run_forever shape as
retention.py and category_usage_monitor.py; reads from
ClientMinuteAggregate (fast, pre-aggregated) rather than raw_events, since
only a per-client byte total is needed, not per-event detail.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity
from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.services import alert_settings_service, insights_service
from app.services.alerting import maybe_alert
from app.services.interval_job import IntervalJob

logger = logging.getLogger(__name__)

ANOMALY_TITLE = "Client exceeded daily data quota"

# At or above 2x the configured quota, this is CRITICAL rather than HIGH --
# matches the existing severity vocabulary used elsewhere in AnomalyEvent.
_CRITICAL_MULTIPLIER = 2


class QuotaMonitorJob(IntervalJob):
    job_name = "quota-monitor"
    failure_source_tag = "quota_monitor"
    failure_log_message = "Quota check failed; will retry next interval"

    def __init__(self, interval_seconds: int = 3600) -> None:
        super().__init__(interval_seconds)

    async def run(self) -> None:
        now = datetime.now(UTC)
        since = now - timedelta(hours=24)

        async with AsyncSessionLocal() as session:
            # Grouped by branch too so each branch's clients are compared
            # against that branch's own quota, not a single global one.
            bytes_by_client = func.sum(ClientMinuteAggregate.total_bytes)
            usage = (
                await session.execute(
                    select(ClientMinuteAggregate.branch, ClientMinuteAggregate.client_ip, bytes_by_client)
                    .where(ClientMinuteAggregate.bucket_ts >= since)
                    .group_by(ClientMinuteAggregate.branch, ClientMinuteAggregate.client_ip)
                )
            ).all()

            anomalies: list[Anomaly] = []
            quota_cache: dict[str, int | None] = {}
            for branch, client_ip, total_bytes in usage:
                if branch not in quota_cache:
                    settings_row = await alert_settings_service.get_settings_row(session, branch)
                    quota_cache[branch] = settings_row.client_daily_byte_quota_bytes
                quota = quota_cache[branch]
                if not quota or total_bytes < quota:
                    continue

                if await self._already_flagged_today(session, client_ip, branch, since):
                    continue
                severity = (
                    AnomalySeverity.CRITICAL
                    if total_bytes >= quota * _CRITICAL_MULTIPLIER
                    else AnomalySeverity.HIGH
                )
                anomalies.append(
                    Anomaly(
                        title=ANOMALY_TITLE,
                        description=(
                            f"{client_ip} used {total_bytes / 1e9:.1f} GB in the last 24h "
                            f"(quota: {quota / 1e9:.1f} GB)."
                        ),
                        severity=severity,
                        client_ip=client_ip,
                        branch=branch,
                        generated_at=now,
                    )
                )

            if not anomalies:
                return

            rows = insights_service.persist(session, anomalies)
            await session.commit()

        for row in rows:
            await maybe_alert(row)

    async def _already_flagged_today(
        self, session: AsyncSession, client_ip: str, branch: str, since: datetime
    ) -> bool:
        """One alert per client per rolling 24h window -- otherwise an
        hourly check would re-flag the same ongoing violation every hour."""
        existing = (
            await session.execute(
                select(AnomalyEvent.id)
                .where(
                    AnomalyEvent.title == ANOMALY_TITLE,
                    AnomalyEvent.client_ip == client_ip,
                    AnomalyEvent.branch == branch,
                    AnomalyEvent.generated_at >= since,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return existing is not None
