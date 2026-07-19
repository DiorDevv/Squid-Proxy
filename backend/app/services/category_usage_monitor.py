"""Periodic check for clients spending too much time in non-work domain
categories in a rolling 24h window (see time_spent_service.get_time_spent_by_category
for the underlying per-category estimate, alert_settings_service.py for the
admin-configurable threshold).

This runs independently of the per-flush anomaly checks in
app/insights/anomaly.py: a meaningful "how many minutes in gaming/social
media today" total can't be computed from a single ~60s aggregator window,
so it needs its own longer-interval background job -- same start/stop/
_run_forever shape as app/services/retention.py.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity
from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service, insights_service
from app.services.alerting import maybe_alert
from app.services.time_spent_service import get_time_spent_by_category

logger = logging.getLogger(__name__)

ANOMALY_TITLE = "Excessive non-work category time"

# Categories that don't count toward the "non-work" total -- everything
# else (gaming, gambling, video/music streaming, social media, shopping,
# news, other) does.
_EXEMPT_CATEGORIES = {DomainCategoryLabel.WORK_TOOLS, DomainCategoryLabel.UNCATEGORIZED}


class CategoryUsageMonitorJob:
    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever(), name="category-usage-monitor")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()

    async def _run_forever(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                break
            except TimeoutError:
                await self._check_catching_errors()

    async def _check_catching_errors(self) -> None:
        """A single bad check must never permanently stop this job -- see
        RetentionJob._purge_catching_errors for the same reasoning."""
        try:
            await self.check()
        except Exception:
            logger.exception("Category usage check failed; will retry next interval")

    async def check(self) -> None:
        now = datetime.now(UTC)
        since = now - timedelta(hours=24)

        async with AsyncSessionLocal() as session:
            settings_row = await alert_settings_service.get_settings_row(session)
            threshold_seconds = settings_row.non_work_minutes_threshold * 60
            if threshold_seconds <= 0:
                return

            client_ips = (
                await session.execute(
                    select(ClientMinuteAggregate.client_ip)
                    .where(ClientMinuteAggregate.bucket_ts >= since)
                    .distinct()
                )
            ).scalars().all()

            anomalies: list[Anomaly] = []
            for client_ip in client_ips:
                if await self._already_flagged_today(session, client_ip, since):
                    continue

                category_items = await get_time_spent_by_category(session, client_ip, since, now)
                non_work_seconds = sum(
                    item.total_seconds for item in category_items if item.category not in _EXEMPT_CATEGORIES
                )
                if non_work_seconds < threshold_seconds:
                    continue

                anomalies.append(
                    Anomaly(
                        title=ANOMALY_TITLE,
                        description=(
                            f"{client_ip} spent {non_work_seconds // 60} minutes in non-work "
                            f"categories over the last 24h (threshold: "
                            f"{settings_row.non_work_minutes_threshold} minutes)."
                        ),
                        severity=AnomalySeverity.MEDIUM,
                        client_ip=client_ip,
                        generated_at=now,
                    )
                )

            if not anomalies:
                return

            rows = insights_service.persist(session, anomalies)
            await session.commit()

        for row in rows:
            await maybe_alert(row)

    async def _already_flagged_today(self, session: AsyncSession, client_ip: str, since: datetime) -> bool:
        """One alert per client per rolling 24h window -- otherwise an
        hourly check would re-flag the same ongoing violation every hour."""
        existing = (
            await session.execute(
                select(AnomalyEvent.id)
                .where(
                    AnomalyEvent.title == ANOMALY_TITLE,
                    AnomalyEvent.client_ip == client_ip,
                    AnomalyEvent.generated_at >= since,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return existing is not None
