"""Raises an anomaly when a watched client IP / domain / user is active
again (see app/models/watchlist_entry.py). Reuses the same
Anomaly -> insights_service.persist -> maybe_alert path as the other
monitor jobs, so a watchlist hit shows up in "Recent anomalies" and goes
out on whatever alert channels are configured.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.insights.base import Anomaly, AnomalySeverity
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.db import AsyncSessionLocal
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.watchlist_entry import WatchlistEntry, WatchlistTargetType
from app.services import insights_service
from app.services.alerting import maybe_alert
from app.services.interval_job import IntervalJob

logger = logging.getLogger(__name__)

_ANOMALY_TITLE = "Watched target active"
# Look back TWICE the interval (plus slack), not just one interval: if a run
# is delayed (a busy event loop, a slow prior run) a one-interval window
# would leave an uncovered gap and silently miss a hit in it. The per-entry
# cooldown means the wider window just re-confirms an ongoing presence
# without re-alerting, so over-covering is free.
_LOOKBACK_SLACK = timedelta(minutes=2)
_LOOKBACK_INTERVALS = 2


class WatchlistMonitorJob(IntervalJob):
    job_name = "watchlist-monitor"
    failure_source_tag = "watchlist_monitor"
    failure_log_message = "Watchlist check failed; will retry next interval"

    def __init__(self, interval_seconds: int = 300) -> None:
        super().__init__(interval_seconds)

    async def run(self) -> None:
        settings = get_settings()
        now = datetime.now(UTC)
        since = (
            now
            - timedelta(seconds=self.interval_seconds * _LOOKBACK_INTERVALS)
            - _LOOKBACK_SLACK
        )
        cooldown = timedelta(seconds=settings.WATCHLIST_ALERT_COOLDOWN_SECONDS)

        async with AsyncSessionLocal() as session:
            entries = (
                await session.execute(
                    select(WatchlistEntry).where(WatchlistEntry.active.is_(True))
                )
            ).scalars().all()
            if not entries:
                return

            anomalies: list[Anomaly] = []
            for entry in entries:
                total, blocked = await self._activity(session, entry, since, now)
                if total == 0:
                    continue
                entry.last_seen_at = now
                if entry.last_alerted_at is not None and now - entry.last_alerted_at < cooldown:
                    continue
                entry.last_alerted_at = now
                anomalies.append(self._anomaly(entry, total, blocked, now))

            if anomalies:
                rows = insights_service.persist(session, anomalies)
                await session.commit()
            else:
                await session.commit()  # persist last_seen_at updates
                return

        for row in rows:
            await maybe_alert(row)

    async def _activity(
        self, session: AsyncSession, entry: WatchlistEntry, since: datetime, now: datetime
    ) -> tuple[int, int]:
        """(request count, blocked count) for this watched target in the
        [since, now] window, read from the pre-aggregated minute tables.

        `entry.value` is stored lower-cased for domains and users (see
        watchlist_service.normalize_value), but the aggregate tables keep
        whatever case Squid logged -- so those two are matched
        case-insensitively via lower(). client_ip is matched as-is (case is
        never meaningful for an IP)."""
        if entry.target_type == WatchlistTargetType.DOMAIN:
            conditions = [
                func.lower(DomainMinuteAggregate.domain) == entry.value,
                DomainMinuteAggregate.bucket_ts >= since,
                DomainMinuteAggregate.bucket_ts <= now,
            ]
            if entry.branch:
                conditions.append(DomainMinuteAggregate.branch == entry.branch)
            stmt = select(
                func.coalesce(func.sum(DomainMinuteAggregate.request_count), 0),
                func.coalesce(func.sum(DomainMinuteAggregate.blocked_count), 0),
            ).where(*conditions)
        else:
            if entry.target_type == WatchlistTargetType.CLIENT_IP:
                match = ClientMinuteAggregate.client_ip == entry.value
            else:
                match = func.lower(ClientMinuteAggregate.user) == entry.value
            conditions = [
                match,
                ClientMinuteAggregate.bucket_ts >= since,
                ClientMinuteAggregate.bucket_ts <= now,
            ]
            if entry.branch:
                conditions.append(ClientMinuteAggregate.branch == entry.branch)
            stmt = select(
                func.coalesce(func.sum(ClientMinuteAggregate.request_count), 0),
                func.coalesce(func.sum(ClientMinuteAggregate.blocked_count), 0),
            ).where(*conditions)

        row = (await session.execute(stmt)).one()
        return int(row[0]), int(row[1])

    def _anomaly(self, entry: WatchlistEntry, total: int, blocked: int, now: datetime) -> Anomaly:
        severity = AnomalySeverity.HIGH if blocked > 0 else AnomalySeverity.MEDIUM
        client_ip = entry.value if entry.target_type == WatchlistTargetType.CLIENT_IP else None
        domain = entry.value if entry.target_type == WatchlistTargetType.DOMAIN else None
        return Anomaly(
            title=_ANOMALY_TITLE,
            description=(
                f"Watched {entry.target_type.value} {entry.value} made {total} request(s) "
                f"({blocked} blocked) in the last interval."
            ),
            severity=severity,
            client_ip=client_ip,
            domain=domain,
            branch=entry.branch or "default",
            generated_at=now,
            kind="watchlist_hit",
            params={
                "targetType": entry.target_type.value,
                "value": entry.value,
                "count": total,
                "blocked": blocked,
            },
        )
