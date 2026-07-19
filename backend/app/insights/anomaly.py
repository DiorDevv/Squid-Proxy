"""Statistical anomaly detection -- the first real InsightsProvider.

Runs once per aggregator flush, over exactly the events that flush just
persisted (see app/services/aggregator.py). Deliberately simple,
threshold-based checks with no ML dependency, consistent with this
project's "portable across SQLite/Postgres, no heavy dependency" approach
elsewhere (see ARCHITECTURE.md).
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity, Insight, InsightsProvider
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import alert_settings_service
from app.services.category_inference import effective_category
from app.services.domain_category_service import get_overrides_map
from app.services.log_parser import ParsedEvent

# A window's request count must exceed this multiple of the historical
# per-window baseline to count as a traffic spike.
TRAFFIC_SPIKE_MULTIPLIER = 3.0
# How many prior minute-buckets to average for that baseline.
TRAFFIC_SPIKE_BASELINE_WINDOWS = 10
# Don't flag spikes until there's enough history to make "baseline" meaningful.
TRAFFIC_SPIKE_MIN_BASELINE_WINDOWS = 5

# A client whose blocked-request ratio in the window is at or above this,
# with at least this many total requests, is flagged.
CLIENT_BLOCKED_RATIO_THRESHOLD = 0.5
CLIENT_BLOCKED_MIN_REQUESTS = 5

# A single event with a corrupted/out-of-order timestamp (clock skew, a
# delayed or replayed log line) must not be able to push window_start
# arbitrarily far into the past -- every "was this seen before
# window_start" query in this file would then trivially treat that flush
# as the first time anything happened, no matter how well-established the
# client/domain actually is. Real aggregator flushes are a few seconds to
# low minutes wide (AGGREGATION_INTERVAL_SECONDS), so an hour is already
# generous slack.
MAX_WINDOW_SPREAD = timedelta(hours=1)


class StatisticalAnomalyProvider(InsightsProvider):
    async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
        return []

    async def detect_anomalies(self, events: list[ParsedEvent], session: AsyncSession) -> list[Anomaly]:
        if not events:
            return []

        window_start = min(e.timestamp for e in events)
        generated_at = max(e.timestamp for e in events)
        if generated_at - window_start > MAX_WINDOW_SPREAD:
            window_start = generated_at - MAX_WINDOW_SPREAD

        anomalies: list[Anomaly] = []
        anomalies += await self._traffic_spike(events, session, window_start, generated_at)
        anomalies += await self._new_blocked_domains(events, session, window_start, generated_at)
        anomalies += self._client_blocked_ratio(events, generated_at)
        anomalies += await self._sensitive_category_visit(events, session, window_start, generated_at)
        return anomalies

    async def _traffic_spike(
        self, events: list[ParsedEvent], session: AsyncSession, window_start: datetime, generated_at: datetime
    ) -> list[Anomaly]:
        history = (
            await session.execute(
                select(MinuteAggregate.total_requests)
                .where(MinuteAggregate.bucket_ts < window_start)
                .order_by(MinuteAggregate.bucket_ts.desc())
                .limit(TRAFFIC_SPIKE_BASELINE_WINDOWS)
            )
        ).scalars().all()
        if len(history) < TRAFFIC_SPIKE_MIN_BASELINE_WINDOWS:
            return []

        baseline = sum(history) / len(history)
        current = len(events)
        if baseline <= 0 or current <= baseline * TRAFFIC_SPIKE_MULTIPLIER:
            return []

        return [
            Anomaly(
                title="Traffic spike detected",
                description=(
                    f"{current} requests in the last window vs. a baseline of "
                    f"~{baseline:.0f} over the previous {len(history)} windows."
                ),
                severity=AnomalySeverity.HIGH,
                generated_at=generated_at,
            )
        ]

    async def _new_blocked_domains(
        self, events: list[ParsedEvent], session: AsyncSession, window_start: datetime, generated_at: datetime
    ) -> list[Anomaly]:
        blocked_domains = {e.domain for e in events if e.blocked and e.domain}
        if not blocked_domains:
            return []

        known = (
            await session.execute(
                select(DomainMinuteAggregate.domain)
                .where(
                    DomainMinuteAggregate.domain.in_(blocked_domains),
                    DomainMinuteAggregate.bucket_ts < window_start,
                )
                .distinct()
            )
        ).scalars().all()
        new_domains = blocked_domains - set(known)

        return [
            Anomaly(
                title="New blocked domain observed",
                description=f"{domain} was blocked for the first time in this window.",
                severity=AnomalySeverity.MEDIUM,
                domain=domain,
                generated_at=generated_at,
            )
            for domain in sorted(new_domains)
        ]

    def _client_blocked_ratio(self, events: list[ParsedEvent], generated_at: datetime) -> list[Anomaly]:
        totals: dict[str, int] = defaultdict(int)
        blocked: dict[str, int] = defaultdict(int)
        for event in events:
            totals[event.client_ip] += 1
            if event.blocked:
                blocked[event.client_ip] += 1

        anomalies: list[Anomaly] = []
        for client_ip, total in totals.items():
            if total < CLIENT_BLOCKED_MIN_REQUESTS:
                continue
            ratio = blocked[client_ip] / total
            if ratio < CLIENT_BLOCKED_RATIO_THRESHOLD:
                continue
            anomalies.append(
                Anomaly(
                    title="Client mostly blocked",
                    description=(
                        f"{client_ip} had {blocked[client_ip]}/{total} requests blocked "
                        f"({ratio:.0%}) in this window."
                    ),
                    severity=AnomalySeverity.HIGH,
                    client_ip=client_ip,
                    generated_at=generated_at,
                )
            )
        return anomalies

    async def _sensitive_category_visit(
        self, events: list[ParsedEvent], session: AsyncSession, window_start: datetime, generated_at: datetime
    ) -> list[Anomaly]:
        """Flags a client's first-ever visit to a domain whose effective
        category (admin override, else category_inference.infer_category)
        is on the admin-configured sensitive list (see
        alert_settings_service.py) -- e.g. "first time this client visited
        a gambling site". Off entirely when no sensitive categories are
        configured (the common case), matching this file's other checks'
        "no signal, no anomaly" default."""
        settings_row = await alert_settings_service.get_settings_row(session)
        sensitive = alert_settings_service.parse_sensitive_categories(settings_row.sensitive_categories)
        if not sensitive:
            return []

        overrides = await get_overrides_map(session)
        candidates = {
            (event.client_ip, event.domain)
            for event in events
            if event.domain and effective_category(event.domain, overrides) in sensitive
        }
        if not candidates:
            return []

        client_ips = {client_ip for client_ip, _ in candidates}
        domains = {domain for _, domain in candidates}
        known_pairs = set(
            (
                await session.execute(
                    select(RawEvent.client_ip, RawEvent.domain)
                    .where(
                        RawEvent.client_ip.in_(client_ips),
                        RawEvent.domain.in_(domains),
                        RawEvent.timestamp < window_start,
                    )
                    .distinct()
                )
            ).all()
        )
        new_pairs = candidates - known_pairs

        return [
            Anomaly(
                title="Sensitive category visited",
                description=(
                    f"{client_ip} visited {domain} "
                    f"({effective_category(domain, overrides).value}) for the first time."
                ),
                severity=AnomalySeverity.MEDIUM,
                client_ip=client_ip,
                domain=domain,
                generated_at=generated_at,
            )
            for client_ip, domain in sorted(new_pairs)
        ]
