import re

from httpx import AsyncClient

from app.services.aggregator import Aggregator
from app.services.event_store import RingBuffer


def _metric_value(body: str, name: str) -> float:
    match = re.search(rf"^{re.escape(name)}(?:\{{[^}}]*\}})? ([0-9.eE+-]+)$", body, re.MULTILINE)
    assert match is not None, f"metric {name!r} not found in:\n{body}"
    return float(match.group(1))


async def test_metrics_is_public(app_client: AsyncClient):
    """/metrics must stay reachable without auth, same trust boundary as
    /api/health -- it's what monitoring infra scrapes."""
    response = await app_client.get("/metrics")
    assert response.status_code == 200


async def test_metrics_returns_prometheus_text_format(app_client: AsyncClient):
    response = await app_client.get("/metrics")
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    for metric in (
        "squid_dashboard_log_lines_seen",
        "squid_dashboard_log_lines_parsed",
        "squid_dashboard_log_parse_failure_rate",
        "squid_dashboard_log_tailer_alive",
        "squid_dashboard_aggregator_backlog_ratio",
        "squid_dashboard_aggregator_events_likely_lost",
        "squid_dashboard_unarchived_purge_branches_count",
    ):
        assert f"# TYPE {metric} gauge" in body


async def test_metrics_matches_health_for_the_same_state(app_client: AsyncClient, test_app):
    """The two endpoints must never silently drift apart -- both read
    build_health_snapshot, so this pins that they report the same numbers
    for the same app.state."""
    ring_buffer = RingBuffer(max_events=10)
    for _ in range(9):
        ring_buffer.append(_fake_event())
    test_app.state.aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    health_body = (await app_client.get("/api/health")).json()
    metrics_body = (await app_client.get("/metrics")).text

    assert _metric_value(metrics_body, "squid_dashboard_aggregator_backlog_ratio") == (
        health_body["aggregator_backlog_ratio"]
    )
    expected_lost = 1.0 if health_body["aggregator_events_likely_lost"] else 0.0
    assert _metric_value(metrics_body, "squid_dashboard_aggregator_events_likely_lost") == expected_lost


def _fake_event():
    from app.services.log_parser import parse_line

    return parse_line(
        "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET "
        "http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    )
