"""Periodic check for clients spending too much time in non-work domain
categories in a rolling 24h window (alert_settings_service.py holds the
admin-configurable threshold).

This runs independently of the per-flush anomaly checks in
app/insights/anomaly.py: a meaningful "how many minutes in gaming/social
media today" total can't be computed from a single ~60s aggregator window,
so it needs its own longer-interval background job -- same start/stop/
_run_forever shape as app/services/retention.py.

Reads client_category_minute_aggregates (populated per-event inside
Aggregator.flush(), see aggregator.py) rather than time_spent_service's
session-based reconstruction over raw_events. That distinction matters at
scale: the old version looped over every active client and re-scanned
raw_events per client, i.e. one full-table scan per client per check --
fine for a handful of clients, not for a real deployment's client count.
This version is a single GROUP BY query regardless of how many clients
there are. The tradeoff is "time spent" becomes a coarser proxy: distinct
minute-buckets with non-work activity, not exact session dwell time. A
single client's precise per-domain breakdown (time_spent_service.py, shown
when an admin opens one client's detail view) is unaffected -- that's an
on-demand, single-client query, not a per-check full scan of everyone.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity
from app.models.anomaly_event import AnomalyEvent
from app.models.client_category_aggregate import ClientCategoryMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service, insights_service
from app.services.alerting import maybe_alert

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
            # Distinct minute-buckets (across every non-exempt category
            # combined, not summed per-category) with any activity for that
            # client -- one query, one full scan of the aggregate table
            # regardless of client count, instead of one raw_events scan
            # per client (see this module's docstring). Grouped by branch
            # too so each branch's clients are compared against that
            # branch's own threshold, not a single global one.
            active_minutes = func.count(func.distinct(ClientCategoryMinuteAggregate.bucket_ts))
            candidates = (
                await session.execute(
                    select(
                        ClientCategoryMinuteAggregate.branch,
                        ClientCategoryMinuteAggregate.client_ip,
                        active_minutes,
                    )
                    .where(
                        ClientCategoryMinuteAggregate.bucket_ts >= since,
                        ClientCategoryMinuteAggregate.category.notin_(_EXEMPT_CATEGORIES),
                    )
                    .group_by(ClientCategoryMinuteAggregate.branch, ClientCategoryMinuteAggregate.client_ip)
                )
            ).all()

            anomalies: list[Anomaly] = []
            threshold_cache: dict[str, int] = {}
            for branch, client_ip, minute_count in candidates:
                if branch not in threshold_cache:
                    settings_row = await alert_settings_service.get_settings_row(session, branch)
                    threshold_cache[branch] = settings_row.non_work_minutes_threshold
                threshold_minutes = threshold_cache[branch]
                if threshold_minutes <= 0 or minute_count < threshold_minutes:
                    continue

                if await self._already_flagged_today(session, client_ip, branch, since):
                    continue

                anomalies.append(
                    Anomaly(
                        title=ANOMALY_TITLE,
                        description=(
                            f"{client_ip} spent {minute_count} minutes in non-work "
                            f"categories over the last 24h (threshold: "
                            f"{threshold_minutes} minutes)."
                        ),
                        severity=AnomalySeverity.MEDIUM,
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
