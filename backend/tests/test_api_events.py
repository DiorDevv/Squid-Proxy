from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
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


async def test_recent_events_includes_raw_log_detail_fields(app_client: AsyncClient, test_app, admin_token, auth_headers):
    test_app.state.ring_buffer.append(_make_event("detail.com"))

    response = await app_client.get("/api/events/recent", headers=auth_headers(admin_token))
    assert response.status_code == 200
    event = response.json()[0]
    assert event["duration_ms"] == 10
    assert event["hierarchy"] == "HIER_DIRECT"
    assert event["peer"] == "1.2.3.4"
    assert event["content_type"] == "text/html"


def _make_raw_event(
    *,
    client_ip: str,
    domain: str,
    blocked: bool = False,
    method: str = "GET",
    user: str | None = "alice",
    timestamp: datetime | None = None,
) -> RawEvent:
    return RawEvent(
        timestamp=timestamp or datetime.now(UTC),
        duration_ms=42,
        client_ip=client_ip,
        action="TCP_DENIED" if blocked else "TCP_MISS",
        status_code=403 if blocked else 200,
        bytes=0 if blocked else 1024,
        method=method,
        url=f"http://{domain}/",
        domain=domain,
        user=user,
        hierarchy="HIER_NONE" if blocked else "HIER_DIRECT",
        peer=None if blocked else "1.2.3.4",
        content_type=None if blocked else "text/html",
        blocked=blocked,
    )


async def test_events_returns_paginated_db_backed_results(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _make_raw_event(client_ip="10.0.1.1", domain="a.com", timestamp=now),
            _make_raw_event(client_ip="10.0.1.2", domain="b.com", timestamp=now - timedelta(minutes=1)),
            _make_raw_event(client_ip="10.0.1.3", domain="c.com", timestamp=now - timedelta(minutes=2)),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/events?limit=2", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    # most recent first
    assert body["items"][0]["domain"] == "a.com"

    page2 = await app_client.get("/api/events?limit=2&offset=2", headers=auth_headers(admin_token))
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["domain"] == "c.com"


async def test_events_blocked_only_filter(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    db_session.add_all(
        [
            _make_raw_event(client_ip="10.0.2.1", domain="allowed.com", blocked=False),
            _make_raw_event(client_ip="10.0.2.1", domain="denied.com", blocked=True),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/events?blocked_only=true", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "denied.com"
    assert body["items"][0]["blocked"] is True


async def test_events_filters_by_domain_method_and_client_ip(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    db_session.add_all(
        [
            _make_raw_event(client_ip="10.0.3.1", domain="match-me.com", method="POST"),
            _make_raw_event(client_ip="10.0.3.1", domain="match-me.com", method="GET"),
            _make_raw_event(client_ip="10.0.3.2", domain="other.com", method="POST"),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/events?domain=match-me&method=POST&client_ip=10.0.3.1",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["client_ip"] == "10.0.3.1"
    assert body["items"][0]["method"] == "POST"


async def test_events_free_text_search_matches_across_fields(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    db_session.add_all(
        [
            _make_raw_event(client_ip="10.0.4.1", domain="findable.com", user="carol"),
            _make_raw_event(client_ip="10.0.4.2", domain="unrelated.com", user="dave"),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/events?search=carol", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "findable.com"


async def test_events_respects_custom_time_range(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _make_raw_event(client_ip="10.0.5.1", domain="recent.com", timestamp=now),
            _make_raw_event(client_ip="10.0.5.1", domain="old.com", timestamp=now - timedelta(days=10)),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/events",
        params={
            "from_ts": (now - timedelta(hours=1)).isoformat(),
            "to_ts": (now + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "recent.com"


async def test_events_returns_raw_log_detail_fields(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    db_session.add(_make_raw_event(client_ip="10.0.6.1", domain="detail.com"))
    await db_session.commit()

    response = await app_client.get("/api/events", headers=auth_headers(admin_token))
    assert response.status_code == 200
    event = response.json()["items"][0]
    assert event["duration_ms"] == 42
    assert event["hierarchy"] == "HIER_DIRECT"
    assert event["peer"] == "1.2.3.4"
    assert event["content_type"] == "text/html"


async def test_events_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/events")
    assert response.status_code == 401
