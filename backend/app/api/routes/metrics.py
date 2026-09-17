"""Prometheus-format exposition of the same operational state /api/health
already reports (see health.build_health_snapshot) -- for wiring into
Grafana/Alertmanager instead of scraping and reshaping /api/health's ad-hoc
JSON. Unauthenticated by default, same trust boundary as /api/health
(README: "All endpoints are under /api, JWT-protected except /api/health")
-- this is for internal monitoring infra to scrape, not exposed publicly
any more than health already is. If METRICS_ALLOWED_IPS is set, this
endpoint is additionally restricted to those client IPs / CIDRs (see
_client_allowed); /api/health stays open regardless (the frontend banner
polls it from browsers).

Design note: these are Gauges set at scrape time from build_health_snapshot,
not persistent Counters incremented at the source. A Prometheus purist would
want a true monotonic Counter for "lines seen" -- that's not done here
because the only source of truth for that number today is itself a
snapshot (LogTailer.lines_seen), not an incrementally-emitted event stream;
inventing a second, independently-incremented counter would risk it
drifting from what /api/health reports for the exact same quantity. A
fresh CollectorRegistry per request (not the global default registry)
avoids cross-test/cross-request state bleed.
"""

import ipaddress
import logging

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from app.api.routes.health import build_health_snapshot
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])

_METRIC_PREFIX = "squid_dashboard"


def _client_allowed(request: Request) -> bool:
    """True unless METRICS_ALLOWED_IPS is set and the peer address isn't in
    it. `request.client.host` is the peer -- which behind a reverse proxy
    running uvicorn with --proxy-headers is the real client's rewritten
    X-Forwarded-For, the same address the rate limiter keys on."""
    allowed = get_settings().METRICS_ALLOWED_IPS
    if not allowed:
        return True
    host = request.client.host if request.client else None
    if host is None:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            logger.warning("Ignoring unparseable METRICS_ALLOWED_IPS entry %r", entry)
    return False


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    if not _client_allowed(request):
        return Response(status_code=403)
    snapshot = build_health_snapshot(request.app)
    registry = CollectorRegistry()

    lines_seen = Gauge(
        f"{_METRIC_PREFIX}_log_lines_seen",
        "Total access.log lines seen by this branch's tailer",
        ["branch"],
        registry=registry,
    )
    lines_parsed = Gauge(
        f"{_METRIC_PREFIX}_log_lines_parsed",
        "Total access.log lines successfully parsed by this branch's tailer",
        ["branch"],
        registry=registry,
    )
    parse_failure_rate = Gauge(
        f"{_METRIC_PREFIX}_log_parse_failure_rate",
        "Fraction of this branch's log lines that failed to parse (0-1)",
        ["branch"],
        registry=registry,
    )
    tailer_alive = Gauge(
        f"{_METRIC_PREFIX}_log_tailer_alive",
        "1 if this branch's log tailer is alive, 0 otherwise",
        ["branch"],
        registry=registry,
    )
    for source in snapshot["log_sources"]:
        lines_seen.labels(branch=source["branch"]).set(source["lines_seen"])
        lines_parsed.labels(branch=source["branch"]).set(source["lines_parsed"])
        parse_failure_rate.labels(branch=source["branch"]).set(source["parse_failure_rate"] or 0.0)
        tailer_alive.labels(branch=source["branch"]).set(1 if source["alive"] else 0)

    Gauge(
        f"{_METRIC_PREFIX}_aggregator_backlog_ratio",
        "Ring-buffer backlog as a fraction of capacity (see Aggregator.backlog_ratio)",
        registry=registry,
    ).set(snapshot["aggregator_backlog_ratio"])
    Gauge(
        f"{_METRIC_PREFIX}_aggregator_events_likely_lost",
        "1 if the aggregator is falling behind enough that events are likely being dropped",
        registry=registry,
    ).set(1 if snapshot["aggregator_events_likely_lost"] else 0)
    Gauge(
        f"{_METRIC_PREFIX}_unarchived_purge_branches_count",
        "Number of branches whose raw_events were purged before being archived on the last retention run",
        registry=registry,
    ).set(len(snapshot["unarchived_purge_branches"]))

    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
