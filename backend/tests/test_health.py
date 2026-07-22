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


async def test_health_reports_no_unarchived_branches_without_a_retention_job(app_client: AsyncClient):
    """The test app's lifespan double doesn't wire up a real retention job --
    the endpoint must degrade to an empty list rather than 500."""
    response = await app_client.get("/api/health")
    body = response.json()
    assert body["unarchived_purge_branches"] == []


async def test_health_reports_unarchived_branches_when_wired(app_client: AsyncClient, test_app):
    from app.services.retention import RetentionJob

    job = RetentionJob()
    job.unarchived_branches = ["hq"]
    test_app.state.retention_job = job

    response = await app_client.get("/api/health")
    body = response.json()
    assert body["unarchived_purge_branches"] == ["hq"]


async def test_health_strict_is_still_200_by_default(app_client: AsyncClient):
    """The plain (non-strict) endpoint must never fail its own frontend
    consumer (useHealthCheck.ts/LogHealthBanner.tsx polls this exact route)
    -- a non-2xx response there makes apiFetch throw instead of returning
    the body, silently hiding the very banner it's meant to drive."""
    response = await app_client.get("/api/health")
    assert response.status_code == 200


async def test_health_strict_returns_503_when_tailer_down(app_client: AsyncClient):
    # The test app's lifespan double wires up a null tailer with is_alive
    # hardcoded false (see conftest.py's _NullTailer) -- exactly the "tailer
    # down" condition strict mode exists to catch.
    response = await app_client.get("/api/health?strict=true")
    assert response.status_code == 503
    body = response.json()
    assert body["log_tailer_alive"] is False


async def test_health_strict_returns_200_when_tailer_alive(app_client: AsyncClient, test_app):
    class _AliveTailer:
        is_alive = True
        lines_seen = 10
        lines_parsed = 10

    test_app.state.log_tailers = {"default": _AliveTailer()}

    response = await app_client.get("/api/health?strict=true")
    assert response.status_code == 200
    assert response.json()["log_tailer_alive"] is True


async def test_health_strict_returns_503_when_events_likely_lost(app_client: AsyncClient, test_app):
    class _AliveTailer:
        is_alive = True
        lines_seen = 10
        lines_parsed = 10

    class _OverflowingAggregator:
        backlog_ratio = 1.0
        events_likely_lost = True

    test_app.state.log_tailers = {"default": _AliveTailer()}
    test_app.state.aggregator = _OverflowingAggregator()

    response = await app_client.get("/api/health?strict=true")
    assert response.status_code == 503


async def test_health_strict_ignores_unarchived_purge_branches(app_client: AsyncClient, test_app):
    """A data-retention warning isn't a "this instance is broken" signal --
    restarting the container wouldn't fix it, so it shouldn't flip the
    healthcheck (unlike a dead tailer or dropped events)."""
    from app.services.retention import RetentionJob

    class _AliveTailer:
        is_alive = True
        lines_seen = 10
        lines_parsed = 10

    job = RetentionJob()
    job.unarchived_branches = ["hq"]
    test_app.state.log_tailers = {"default": _AliveTailer()}
    test_app.state.retention_job = job

    response = await app_client.get("/api/health?strict=true")
    assert response.status_code == 200


def _fake_event():
    from app.services.log_parser import parse_line

    return parse_line(
        "1737100800.123 45 10.0.0.5 TCP_MISS/200 1024 GET "
        "http://example.com/ alice HIER_DIRECT/93.184.216.34 text/html"
    )
