"""Statistical anomaly detection -- the first real InsightsProvider.

Runs once per aggregator flush, over exactly the events that flush just
persisted (see app/services/aggregator.py). Deliberately simple,
threshold-based checks with no ML dependency, consistent with this
project's "portable across SQLite/Postgres, no heavy dependency" approach
elsewhere (see ARCHITECTURE.md).
"""

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity, Insight, InsightsProvider
from app.models.alert_rule import AlertRule, AlertRuleMetric, AlertRuleScope
from app.models.anomaly_event import AnomalyEvent
from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate
from app.models.raw_event import RawEvent
from app.services import alert_settings_service
from app.services.category_inference import effective_category
from app.services.domain_category_service import get_overrides_map
from app.services.log_parser import ParsedEvent

# A window is a traffic spike when its request count clears a robust upper
# bound built from recent history: the greater of (median + K*MAD) -- which
# widens when the stream is normally noisy -- and a plain multiple of the
# median, so a very regular stream (MAD ~= 0) still needs a real jump, not a
# one-request wobble. Median/MAD is used rather than mean/stdev so a single
# earlier spike in the baseline window can't drag the bar out of reach.
TRAFFIC_SPIKE_MULTIPLIER = 3.0
TRAFFIC_SPIKE_MAD_K = 5.0
# How many prior minute-buckets to pull for that baseline. ~30 is enough
# for a stable median without reaching so far back that a different traffic
# regime leaks in.
TRAFFIC_SPIKE_BASELINE_WINDOWS = 30
# Don't flag spikes until there's enough history to make median/MAD meaningful.
TRAFFIC_SPIKE_MIN_BASELINE_WINDOWS = 5
# Below this many requests in the window, "3x the median" is still just
# noise on a quiet branch -- never flag a spike under it.
TRAFFIC_SPIKE_MIN_ABSOLUTE = 25

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

# Field name for each metric on ClientMinuteAggregate/DomainMinuteAggregate
# (identical on both) vs. MinuteAggregate (branch-level totals use
# different names for the same concepts -- see app/models/minute_aggregate.py).
_ENTITY_METRIC_FIELD: dict[AlertRuleMetric, str] = {
    AlertRuleMetric.REQUEST_COUNT: "request_count",
    AlertRuleMetric.BLOCKED_COUNT: "blocked_count",
    AlertRuleMetric.TOTAL_BYTES: "total_bytes",
    AlertRuleMetric.BYTES_RECEIVED: "bytes_received",
}
_BRANCH_METRIC_FIELD: dict[AlertRuleMetric, str] = {
    AlertRuleMetric.REQUEST_COUNT: "total_requests",
    AlertRuleMetric.BLOCKED_COUNT: "blocked_requests",
    AlertRuleMetric.TOTAL_BYTES: "total_bytes",
    AlertRuleMetric.BYTES_RECEIVED: "bytes_received",
}

# detect_anomalies runs every aggregator flush (~AGGREGATION_INTERVAL_SECONDS).
# A condition that persists across many flushes -- a spike that lasts ten
# minutes, a client that stays mostly-blocked for an hour -- would otherwise
# raise a near-identical anomaly on every one of them. Once a check has fired
# for a given (kind, branch, and client_ip/domain where it has one), it stays
# quiet for this long. The periodic monitors (quota, uncategorized-domain,
# ...) already do their own equivalent; this is the same idea for the
# per-flush statistical checks.
STATISTICAL_ANOMALY_COOLDOWN = timedelta(hours=1)


class StatisticalAnomalyProvider(InsightsProvider):
    async def analyze_window(self, events: list[ParsedEvent]) -> list[Insight]:
        return []

    async def detect_anomalies(self, events: list[ParsedEvent], session: AsyncSession) -> list[Anomaly]:
        if not events:
            return []

        # A flush window can contain events from more than one branch (each
        # branch has its own LogTailer, all feeding the same ring buffer --
        # see ARCHITECTURE.md). Every check below is computed once per
        # branch, scoped to that branch's own history/baseline, so one
        # branch's traffic never masks or distorts another's.
        by_branch: dict[str, list[ParsedEvent]] = defaultdict(list)
        for event in events:
            by_branch[event.branch].append(event)

        anomalies: list[Anomaly] = []
        for branch, branch_events in by_branch.items():
            window_start = min(e.timestamp for e in branch_events)
            generated_at = max(e.timestamp for e in branch_events)
            if generated_at - window_start > MAX_WINDOW_SPREAD:
                window_start = generated_at - MAX_WINDOW_SPREAD

            anomalies += await self._traffic_spike(branch_events, session, window_start, generated_at, branch)
            anomalies += await self._new_blocked_domains(
                branch_events, session, window_start, generated_at, branch
            )
            anomalies += await self._client_blocked_ratio(branch_events, session, generated_at, branch)
            anomalies += await self._sensitive_category_visit(
                branch_events, session, window_start, generated_at, branch
            )
            anomalies += await self._custom_rules(branch_events, session, generated_at, branch)
        return anomalies

    async def _recently_flagged(
        self,
        session: AsyncSession,
        kind: str,
        branch: str,
        now: datetime,
        *,
        client_ip: str | None = None,
        domain: str | None = None,
    ) -> bool:
        """True if an anomaly of this kind for this same target was already
        raised within STATISTICAL_ANOMALY_COOLDOWN. `now` is the window's
        latest event timestamp (this file works in event time, not wall
        clock), matching how the rows being queried were stamped."""
        conditions = [
            AnomalyEvent.kind == kind,
            AnomalyEvent.branch == branch,
            AnomalyEvent.generated_at >= now - STATISTICAL_ANOMALY_COOLDOWN,
        ]
        if client_ip is not None:
            conditions.append(AnomalyEvent.client_ip == client_ip)
        if domain is not None:
            conditions.append(AnomalyEvent.domain == domain)
        existing = (
            await session.execute(select(AnomalyEvent.id).where(*conditions).limit(1))
        ).scalar_one_or_none()
        return existing is not None

    async def _traffic_spike(
        self,
        events: list[ParsedEvent],
        session: AsyncSession,
        window_start: datetime,
        generated_at: datetime,
        branch: str,
    ) -> list[Anomaly]:
        history = (
            await session.execute(
                select(MinuteAggregate.total_requests)
                .where(MinuteAggregate.bucket_ts < window_start, MinuteAggregate.branch == branch)
                .order_by(MinuteAggregate.bucket_ts.desc())
                .limit(TRAFFIC_SPIKE_BASELINE_WINDOWS)
            )
        ).scalars().all()
        if len(history) < TRAFFIC_SPIKE_MIN_BASELINE_WINDOWS:
            return []

        current = len(events)
        if current < TRAFFIC_SPIKE_MIN_ABSOLUTE:
            return []

        median = statistics.median(history)
        if median <= 0:
            return []
        mad = statistics.median([abs(count - median) for count in history])
        threshold = max(median + TRAFFIC_SPIKE_MAD_K * mad, median * TRAFFIC_SPIKE_MULTIPLIER)
        if current <= threshold:
            return []
        if await self._recently_flagged(session, "traffic_spike", branch, generated_at):
            return []

        return [
            Anomaly(
                title="Traffic spike detected",
                description=(
                    f"{current} requests in the last window vs. a baseline of "
                    f"~{median:.0f} over the previous {len(history)} windows."
                ),
                severity=AnomalySeverity.HIGH,
                branch=branch,
                generated_at=generated_at,
                kind="traffic_spike",
                params={"current": current, "baseline": round(median), "windows": len(history)},
            )
        ]

    async def _new_blocked_domains(
        self,
        events: list[ParsedEvent],
        session: AsyncSession,
        window_start: datetime,
        generated_at: datetime,
        branch: str,
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
                    DomainMinuteAggregate.branch == branch,
                )
                .distinct()
            )
        ).scalars().all()
        new_domains = blocked_domains - set(known)

        anomalies: list[Anomaly] = []
        for domain in sorted(new_domains):
            if await self._recently_flagged(
                session, "new_blocked_domain", branch, generated_at, domain=domain
            ):
                continue
            anomalies.append(
                Anomaly(
                    title="New blocked domain observed",
                    description=f"{domain} was blocked for the first time in this window.",
                    severity=AnomalySeverity.MEDIUM,
                    domain=domain,
                    branch=branch,
                    generated_at=generated_at,
                    kind="new_blocked_domain",
                    params={"domain": domain},
                )
            )
        return anomalies

    async def _client_blocked_ratio(
        self, events: list[ParsedEvent], session: AsyncSession, generated_at: datetime, branch: str
    ) -> list[Anomaly]:
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
            if await self._recently_flagged(
                session, "client_blocked_ratio", branch, generated_at, client_ip=client_ip
            ):
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
                    branch=branch,
                    generated_at=generated_at,
                    kind="client_blocked_ratio",
                    params={
                        "clientIp": client_ip,
                        "blocked": blocked[client_ip],
                        "total": total,
                        "ratio": round(ratio * 100),
                    },
                )
            )
        return anomalies

    async def _sensitive_category_visit(
        self,
        events: list[ParsedEvent],
        session: AsyncSession,
        window_start: datetime,
        generated_at: datetime,
        branch: str,
    ) -> list[Anomaly]:
        """Flags a client's first-ever visit to a domain whose effective
        category (admin override, else category_inference.infer_category)
        is on the admin-configured sensitive list (see
        alert_settings_service.py) -- e.g. "first time this client visited
        a gambling site". Off entirely when no sensitive categories are
        configured for this branch (the common case), matching this file's
        other checks' "no signal, no anomaly" default."""
        settings_row = await alert_settings_service.get_settings_row(session, branch)
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
                        RawEvent.branch == branch,
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
                branch=branch,
                generated_at=generated_at,
                kind="sensitive_category_visit",
                params={
                    "clientIp": client_ip,
                    "domain": domain,
                    "category": effective_category(domain, overrides).value,
                },
            )
            for client_ip, domain in sorted(new_pairs)
        ]

    async def _custom_rules(
        self,
        events: list[ParsedEvent],
        session: AsyncSession,
        generated_at: datetime,
        branch: str,
    ) -> list[Anomaly]:
        """Admin-defined threshold rules (Settings -> Alerts -> Custom
        rules, see app/models/alert_rule.py) -- the generic escape hatch
        for "flag a client_ip/domain/branch whose <metric> exceeds
        <threshold> within a trailing window", without a code change per
        new rule. Only evaluates client_ips/domains actually seen in this
        flush (same scoping as the other per-flush checks above); a
        branch-scope rule always evaluates once regardless."""
        rules = (
            await session.execute(
                select(AlertRule).where(AlertRule.branch == branch, AlertRule.enabled.is_(True))
            )
        ).scalars().all()
        if not rules:
            return []

        client_ips = {e.client_ip for e in events if e.client_ip}
        domains = {e.domain for e in events if e.domain}

        anomalies: list[Anomaly] = []
        for rule in rules:
            if rule.scope == AlertRuleScope.CLIENT_IP:
                values = await self._sum_entity_metric(
                    session, ClientMinuteAggregate, ClientMinuteAggregate.client_ip,
                    rule, branch, client_ips, generated_at,
                )
            elif rule.scope == AlertRuleScope.DOMAIN:
                values = await self._sum_entity_metric(
                    session, DomainMinuteAggregate, DomainMinuteAggregate.domain,
                    rule, branch, domains, generated_at,
                )
            else:
                values = await self._sum_branch_metric(session, rule, branch, generated_at)

            for target, value in values.items():
                if value <= rule.threshold:
                    continue
                kind = f"custom_rule_{rule.id}"
                dedup_kwargs = (
                    {"client_ip": target}
                    if rule.scope == AlertRuleScope.CLIENT_IP
                    else {"domain": target}
                    if rule.scope == AlertRuleScope.DOMAIN
                    else {}
                )
                if await self._recently_flagged(session, kind, branch, generated_at, **dedup_kwargs):
                    continue

                anomalies.append(
                    Anomaly(
                        title=rule.name,
                        description=(
                            f"{target} reached {value} ({rule.metric.value}) in the last "
                            f"{rule.window_minutes} min (threshold: {rule.threshold})."
                        ),
                        severity=rule.severity,
                        client_ip=target if rule.scope == AlertRuleScope.CLIENT_IP else None,
                        domain=target if rule.scope == AlertRuleScope.DOMAIN else None,
                        branch=branch,
                        generated_at=generated_at,
                        kind=kind,
                        params={
                            "ruleName": rule.name,
                            "scope": rule.scope.value,
                            "metric": rule.metric.value,
                            "target": target,
                            "value": int(value),
                            "threshold": int(rule.threshold),
                            "windowMinutes": rule.window_minutes,
                        },
                    )
                )
        return anomalies

    async def _sum_entity_metric(
        self,
        session: AsyncSession,
        model: type[ClientMinuteAggregate] | type[DomainMinuteAggregate],
        key_col: Any,
        rule: AlertRule,
        branch: str,
        targets: set[str],
        generated_at: datetime,
    ) -> dict[str, int]:
        """One grouped query per rule (not one per target) -- sums
        `rule.metric` over the trailing window for every client_ip/domain
        seen in this flush at once."""
        if not targets:
            return {}
        since = generated_at - timedelta(minutes=rule.window_minutes)
        metric_col = getattr(model, _ENTITY_METRIC_FIELD[rule.metric])
        rows = (
            await session.execute(
                select(key_col, func.sum(metric_col))
                .where(
                    model.branch == branch,
                    key_col.in_(targets),
                    model.bucket_ts >= since,
                    model.bucket_ts <= generated_at,
                )
                .group_by(key_col)
            )
        ).all()
        return {key: int(total) for key, total in rows}

    async def _sum_branch_metric(
        self, session: AsyncSession, rule: AlertRule, branch: str, generated_at: datetime
    ) -> dict[str, int]:
        since = generated_at - timedelta(minutes=rule.window_minutes)
        metric_col = getattr(MinuteAggregate, _BRANCH_METRIC_FIELD[rule.metric])
        total = (
            await session.execute(
                select(func.coalesce(func.sum(metric_col), 0)).where(
                    MinuteAggregate.branch == branch,
                    MinuteAggregate.bucket_ts >= since,
                    MinuteAggregate.bucket_ts <= generated_at,
                )
            )
        ).scalar_one()
        return {branch: int(total)}
