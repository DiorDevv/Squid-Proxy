from httpx import AsyncClient


async def test_response_always_carries_a_request_id(app_client: AsyncClient):
    response = await app_client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


async def test_client_supplied_request_id_is_echoed_back_unchanged(app_client: AsyncClient):
    response = await app_client.get("/api/health", headers={"X-Request-ID": "test-request-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"


async def test_two_requests_get_different_generated_request_ids(app_client: AsyncClient):
    first = await app_client.get("/api/health")
    second = await app_client.get("/api/health")
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
