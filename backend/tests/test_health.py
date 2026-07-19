from httpx import AsyncClient


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
