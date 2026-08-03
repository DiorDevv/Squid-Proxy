"""Prometheus-format exposition of the same operational state /api/health
already reports (see health.build_health_snapshot) -- for wiring into
Grafana/Alertmanager instead of scraping and reshaping /api/health's ad-hoc
JSON. Deliberately unauthenticated, same trust boundary as /api/health
(README: "All endpoints are under /api, JWT-protected except /api/health")
-- this is for internal monitoring infra to scrape, not exposed publicly
any more than health already is.

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

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from app.api.routes.health import build_health_snapshot

router = APIRouter(tags=["metrics"])

_METRIC_PREFIX = "squid_dashboard"


@router.get("/metrics")
async def metrics(request: Request) -> Response:
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
