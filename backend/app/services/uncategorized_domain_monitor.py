"""Periodic check for high-traffic domains that stayed uncategorized --
neither an admin override, the curated hostname list, the UT1 bulk
blacklist, nor the TLD/keyword fallback recognized them (see
category_inference.py).

This exists because "review every uncategorized domain" doesn't scale for a
real deployment (potentially hundreds of distinct domains), but reviewing
them isn't actually necessary either: real traffic follows a Zipf-like
distribution where a handful of domains account for most of the volume, so
flagging only the ones that cleared a request-count threshold turns "look
through everything" into "glance at a handful a day" -- the same shape as
category_usage_monitor.py's "only surface what actually crossed a
threshold" approach, just for domains instead of clients.

Off by default per branch (uncategorized_domain_request_threshold is None
until an admin sets one via /api/alert-settings) -- a fresh deployment
shouldn't start generating anomalies for a check nobody asked for.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.insights.base import Anomaly, AnomalySeverity
from app.models.anomaly_event import AnomalyEvent
from app.models.db import AsyncSessionLocal
from app.models.domain_category import DomainCategoryLabel
from app.services import alert_settings_service, insights_service, stats_service
from app.services.alerting import maybe_alert
from app.services.interval_job import IntervalJob

logger = logging.getLogger(__name__)

ANOMALY_TITLE = "High-traffic domain uncategorized"

# How many of the top uncategorized-by-volume domains to even look at per
# branch per check -- the threshold filters out all but a handful in
# practice, this just bounds the query itself.
_CANDIDATE_LIMIT = 20

# Once flagged, a domain won't be flagged again for this branch until this
# many days have passed -- otherwise a domain that stays uncategorized
# (nobody's gotten around to labeling it yet) would re-trigger every single
# check, which is noise, not signal.
_RE_FLAG_COOLDOWN_DAYS = 7


class UncategorizedDomainMonitorJob(IntervalJob):
    job_name = "uncategorized-domain-monitor"
    failure_source_tag = "uncategorized_domain_monitor"
    failure_log_message = "Uncategorized-domain check failed; will retry next interval"

    def __init__(self, interval_seconds: int = 86400) -> None:
        super().__init__(interval_seconds)

    async def run(self) -> None:
        settings = get_settings()
        now = datetime.now(UTC)
        since = now - timedelta(hours=24)

        async with AsyncSessionLocal() as session:
            anomalies: list[Anomaly] = []
            for source in settings.effective_log_sources:
                branch = source.branch
                settings_row = await alert_settings_service.get_settings_row(session, branch)
                threshold = settings_row.uncategorized_domain_request_threshold
                if not threshold or threshold <= 0:
                    continue

                top_uncategorized = await stats_service.get_top_domains(
                    session,
                    since,
                    now,
                    limit=_CANDIDATE_LIMIT,
                    order_by="requests",
                    category=DomainCategoryLabel.UNCATEGORIZED,
                    branch=branch,
                )

                for stat in top_uncategorized:
                    if stat.request_count < threshold:
                        continue
                    if await self._recently_flagged(session, stat.domain, branch, now):
                        continue

                    anomalies.append(
                        Anomaly(
                            title=ANOMALY_TITLE,
                            description=(
                                f"{stat.domain} had {stat.request_count} requests in the last 24h "
                                f"but has no assigned category (threshold: {threshold})."
                            ),
                            severity=AnomalySeverity.LOW,
                            domain=stat.domain,
                            branch=branch,
                            generated_at=now,
                            kind="uncategorized_domain_high_traffic",
                            params={
                                "domain": stat.domain,
                                "requests": stat.request_count,
                                "threshold": threshold,
                            },
                        )
                    )

            if not anomalies:
                return

            rows = insights_service.persist(session, anomalies)
            await session.commit()

        for row in rows:
            await maybe_alert(row)

    async def _recently_flagged(
        self, session: AsyncSession, domain: str, branch: str, now: datetime
    ) -> bool:
        cutoff = now - timedelta(days=_RE_FLAG_COOLDOWN_DAYS)
        existing = (
            await session.execute(
                select(AnomalyEvent.id)
                .where(
                    AnomalyEvent.title == ANOMALY_TITLE,
                    AnomalyEvent.domain == domain,
                    AnomalyEvent.branch == branch,
                    AnomalyEvent.generated_at >= cutoff,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return existing is not None
