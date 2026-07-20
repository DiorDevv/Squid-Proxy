from httpx import AsyncClient

from app.services.aggregator import Aggregator
from app.services.event_store import RingBuffer


async def test_health_reports_no_data_yet_as_null_failure_rate(app_client: AsyncClient):
    response = await app_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["log_lines_seen"] == 0
    assert body["log_parse_failure_rate"] is None


async def test_health_is_public(app_client: AsyncClient):
    """/api/health must stay reachable without auth -- it's what an
    operator (or a monitoring probe) checks *before* trusting the rest of
    the app, including whether login even works."""
    response = await app_client.get("/api/health")
    assert response.status_code == 200


async def test_health_reports_zero_backlog_without_an_aggregator(app_client: AsyncClient):
    """The test app's lifespan double doesn't wire up a real aggregator --
    the endpoint must degrade to a harmless default rather than 500."""
    response = await app_client.get("/api/health")
    body = response.json()
    assert body["aggregator_backlog_ratio"] == 0.0
    assert body["aggregator_events_likely_lost"] is False


async def test_health_reports_aggregator_backlog_when_wired(app_client: AsyncClient, test_app):
    ring_buffer = RingBuffer(max_events=10)
    for _ in range(9):
        ring_buffer.append(_fake_event())
    test_app.state.aggregator = Aggregator(ring_buffer=ring_buffer, interval_seconds=60)

    response = await app_client.get("/api/health")
    body = response.json()
    assert body["aggregator_backlog_ratio"] == 0.9
    assert body["aggregator_events_likely_lost"] is False


def _fake_event():
    from app.services.log_parser import parse_line

    return parse_line(
        "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET "
        "http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    )
