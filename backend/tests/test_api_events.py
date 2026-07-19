from httpx import AsyncClient

from app.services.log_parser import parse_line


def _make_event(domain: str, blocked: bool = False):
    action_status = "TCP_DENIED/403" if blocked else "TCP_MISS/200"
    line = f"1737100800.123 10 10.0.0.5 {action_status} 100 GET http://{domain}/ alice HIER_DIRECT/1.2.3.4 text/html"
    return parse_line(line)


async def test_recent_events_returns_seeded_ring_buffer_events(app_client: AsyncClient, test_app, admin_token, auth_headers):
    test_app.state.ring_buffer.append(_make_event("one.com"))
    test_app.state.ring_buffer.append(_make_event("two.com"))

    response = await app_client.get("/api/events/recent", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # most recent first
    assert body[0]["domain"] == "two.com"


async def test_recent_events_blocked_only_filter(app_client: AsyncClient, test_app, admin_token, auth_headers):
    test_app.state.ring_buffer.append(_make_event("allowed.com", blocked=False))
    test_app.state.ring_buffer.append(_make_event("blocked.com", blocked=True))

    response = await app_client.get("/api/events/recent?blocked_only=true", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["domain"] == "blocked.com"
    assert body[0]["blocked"] is True


async def test_recent_events_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/events/recent")
    assert response.status_code == 401
