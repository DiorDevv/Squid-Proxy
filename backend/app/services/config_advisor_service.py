"""Detects common Squid misconfigurations from the last 24h of aggregates.

This is advisory, not authoritative -- every check is a heuristic over
data that is already aggregated, so it is cheap and never scans raw
events. It stays quiet (empty `findings`) for a well-configured, well-fed
deployment; a finding means "worth a look at squid.conf", not "broken".
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.schemas.config_advisor import ConfigAdvisorResponse, ConfigFinding
from app.services.category_inference import effective_category
from app.services.domain_category_service import get_overrides_map

_WINDOW_HOURS = 24
# Below this many requests in the window the checks are noise -- a nearly
# idle install shouldn't be told its ACLs are too permissive.
_MIN_REQUESTS = 500
_SENSITIVE_CATEGORIES = {DomainCategoryLabel.GAMBLING, DomainCategoryLabel.ADULT_CONTENT}


async def analyze(session: AsyncSession, branch: str | None) -> ConfigAdvisorResponse:
    now = datetime.now(UTC)
    since = now - timedelta(hours=_WINDOW_HOURS)

    min_conditions = [MinuteAggregate.bucket_ts >= since, MinuteAggregate.bucket_ts <= now]
    if branch is not None:
        min_conditions.append(MinuteAggregate.branch == branch)
    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(MinuteAggregate.total_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.blocked_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.hit_requests), 0),
                func.coalesce(func.sum(MinuteAggregate.miss_requests), 0),
            ).where(*min_conditions)
        )
    ).one()
    total_requests, blocked, hit, miss = (int(v) for v in totals)

    findings: list[ConfigFinding] = []
    if total_requests < _MIN_REQUESTS:
        return ConfigAdvisorResponse(
            checked_at=now,
            window_hours=_WINDOW_HOURS,
            total_requests=total_requests,
            findings=findings,
        )

    # --- Caching: cacheable traffic exists but almost none of it is a hit
    cacheable = hit + miss
    if cacheable >= _MIN_REQUESTS:
        hit_ratio = hit / cacheable
        if hit_ratio < 0.02:
            findings.append(
                ConfigFinding(code="no_caching", severity="warning", value=round(hit_ratio, 4))
            )

    # --- Blocking: a filtering proxy that never denies anything
    denied_ratio = blocked / total_requests
    if denied_ratio < 0.001:
        findings.append(
            ConfigFinding(code="no_denies", severity="info", value=round(denied_ratio, 4))
        )

    # --- Proxy auth: share of requests with no user attribution
    client_conditions = [
        ClientMinuteAggregate.bucket_ts >= since,
        ClientMinuteAggregate.bucket_ts <= now,
    ]
    if branch is not None:
        client_conditions.append(ClientMinuteAggregate.branch == branch)
    total_client, anon_client = (
        await session.execute(
            select(
                func.coalesce(func.sum(ClientMinuteAggregate.request_count), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (ClientMinuteAggregate.user.is_(None), ClientMinuteAggregate.request_count),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(*client_conditions)
        )
    ).one()
    total_client, anon_client = int(total_client), int(anon_client)
    if total_client >= _MIN_REQUESTS:
        anon_ratio = anon_client / total_client
        if anon_ratio > 0.98:
            findings.append(
                ConfigFinding(code="no_proxy_auth", severity="info", value=round(anon_ratio, 4))
            )

    # --- Per-domain checks (dominance, sensitive-allowed)
    dom_conditions = [
        DomainMinuteAggregate.bucket_ts >= since,
        DomainMinuteAggregate.bucket_ts <= now,
    ]
    if branch is not None:
        dom_conditions.append(DomainMinuteAggregate.branch == branch)
    dom_rows = (
        await session.execute(
            select(
                DomainMinuteAggregate.domain,
                func.sum(DomainMinuteAggregate.request_count),
                func.sum(DomainMinuteAggregate.blocked_count),
            )
            .where(*dom_conditions)
            .group_by(DomainMinuteAggregate.domain)
        )
    ).all()
    overrides = await get_overrides_map(session)
    domain_total = sum(int(r[1]) for r in dom_rows)
    sensitive_allowed = 0
    top_domain: tuple[str, int] | None = None
    for domain, req, blk in dom_rows:
        req, blk = int(req), int(blk)
        if top_domain is None or req > top_domain[1]:
            top_domain = (domain, req)
        if effective_category(domain, overrides) in _SENSITIVE_CATEGORIES:
            sensitive_allowed += max(0, req - blk)

    if sensitive_allowed >= 20:
        findings.append(
            ConfigFinding(
                code="sensitive_allowed", severity="warning", value=float(sensitive_allowed)
            )
        )
    if top_domain is not None and domain_total > 0:
        share = top_domain[1] / domain_total
        if share > 0.6:
            findings.append(
                ConfigFinding(
                    code="single_domain_dominant",
                    severity="info",
                    value=round(share, 4),
                    detail=top_domain[0],
                )
            )

    return ConfigAdvisorResponse(
        checked_at=now,
        window_hours=_WINDOW_HOURS,
        total_requests=total_requests,
        findings=findings,
    )
