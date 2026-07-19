from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.raw_event import RawEvent


async def _seed_clients(db_session: AsyncSession) -> None:
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=bucket, client_ip="10.0.0.1", user="alice", request_count=100, blocked_count=5
            ),
            ClientMinuteAggregate(
                bucket_ts=bucket, client_ip="10.0.0.2", user="bob", request_count=20, blocked_count=15
            ),
        ]
    )
    await db_session.commit()


async def test_list_clients_sorted_by_total_requests_desc(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_clients(db_session)

    response = await app_client.get(
        "/api/clients?range=1h&sort_by=total_requests&order=desc", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["client_ip"] == "10.0.0.1"
    assert body["items"][0]["total_requests"] == 100


async def test_list_clients_sorted_by_blocked_requests_desc(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_clients(db_session)

    response = await app_client.get(
        "/api/clients?range=1h&sort_by=blocked_requests&order=desc", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["client_ip"] == "10.0.0.2"


async def test_list_clients_pagination(app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers):
    await _seed_clients(db_session)

    response = await app_client.get("/api/clients?range=1h&limit=1&offset=1", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 2


async def test_list_clients_search_filters_by_ip_and_reports_matching_total(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_clients(db_session)

    response = await app_client.get(
        "/api/clients?range=1h&search=10.0.0.1", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    # total must reflect the filtered count, not the unfiltered one -- this
    # is what keeps the frontend's "page X of Y / N total" footer honest.
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["client_ip"] == "10.0.0.1"


async def test_list_clients_search_filters_by_user_case_insensitively(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_clients(db_session)

    response = await app_client.get(
        "/api/clients?range=1h&search=ALICE", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["user"] == "alice"


async def test_list_clients_search_with_no_matches_returns_empty_page(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_clients(db_session)

    response = await app_client.get(
        "/api/clients?range=1h&search=no-such-client", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_client_activity_returns_events_for_that_ip_only(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            RawEvent(
                timestamp=now,
                duration_ms=10,
                client_ip="10.0.0.1",
                action="TCP_MISS",
                status_code=200,
                bytes=100,
                method="GET",
                url="http://example.com/",
                domain="example.com",
                user="alice",
                hierarchy="HIER_DIRECT",
                peer="1.2.3.4",
                content_type="text/html",
                blocked=False,
            ),
            RawEvent(
                timestamp=now - timedelta(minutes=1),
                duration_ms=5,
                client_ip="10.0.0.2",
                action="TCP_DENIED",
                status_code=403,
                bytes=0,
                method="GET",
                url="http://blocked.com/",
                domain="blocked.com",
                user="bob",
                hierarchy="HIER_NONE",
                peer=None,
                content_type=None,
                blocked=True,
            ),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/clients/10.0.0.1/activity", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "example.com"


async def test_client_activity_blocked_only_filter(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            RawEvent(
                timestamp=now,
                duration_ms=1,
                client_ip="10.0.0.9",
                action="TCP_MISS",
                status_code=200,
                bytes=1,
                method="GET",
                url="http://allowed.com/",
                domain="allowed.com",
                user=None,
                hierarchy=None,
                peer=None,
                content_type=None,
                blocked=False,
            ),
            RawEvent(
                timestamp=now,
                duration_ms=1,
                client_ip="10.0.0.9",
                action="TCP_DENIED",
                status_code=403,
                bytes=0,
                method="GET",
                url="http://denied.com/",
                domain="denied.com",
                user=None,
                hierarchy=None,
                peer=None,
                content_type=None,
                blocked=True,
            ),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/clients/10.0.0.9/activity?blocked_only=true", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "denied.com"


async def test_client_summary_route_rolls_up_all_users_for_the_ip(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            ClientMinuteAggregate(
                bucket_ts=bucket,
                client_ip="10.0.0.5",
                user="alice",
                request_count=10,
                blocked_count=1,
                total_bytes=1000,
            ),
            ClientMinuteAggregate(
                bucket_ts=bucket,
                client_ip="10.0.0.5",
                user="bob",
                request_count=5,
                blocked_count=0,
                total_bytes=500,
            ),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/clients/10.0.0.5/summary?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["client_ip"] == "10.0.0.5"
    assert body["total_requests"] == 15
    assert body["blocked_requests"] == 1
    assert body["total_bytes"] == 1500


async def test_client_summary_route_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/clients/10.0.0.5/summary")
    assert response.status_code == 401


async def _activity_event(client_ip: str, timestamp, domain: str, method: str = "GET", blocked: bool = False):
    return RawEvent(
        timestamp=timestamp,
        duration_ms=1,
        client_ip=client_ip,
        action="TCP_DENIED" if blocked else "TCP_MISS",
        status_code=403 if blocked else 200,
        bytes=100,
        method=method,
        url=f"http://{domain}/",
        domain=domain,
        user=None,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=blocked,
    )


async def test_client_activity_route_filters_by_domain_search(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _activity_event("10.0.0.7", now, "wikipedia.org"),
            await _activity_event("10.0.0.7", now, "github.com"),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/clients/10.0.0.7/activity?domain=wiki", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "wikipedia.org"


async def test_client_activity_route_filters_by_method(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _activity_event("10.0.0.8", now, "example.com", method="GET"),
            await _activity_event("10.0.0.8", now, "example.com", method="POST"),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/clients/10.0.0.8/activity?method=POST", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["method"] == "POST"


async def test_client_activity_route_respects_custom_time_range(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    old_event = await _activity_event("10.0.0.9", now - timedelta(days=10), "old.example")
    recent_event = await _activity_event("10.0.0.9", now, "recent.example")
    db_session.add_all([old_event, recent_event])
    await db_session.commit()

    response = await app_client.get(
        "/api/clients/10.0.0.9/activity?range=1h", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "recent.example"


async def test_client_time_spent_by_category_route(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _activity_event("10.0.0.11", now, "youtube.com"),
            await _activity_event("10.0.0.11", now - timedelta(minutes=5), "youtube.com"),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/clients/10.0.0.11/time-spent-by-category?range=1h", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert any(item["category"] == "video_streaming" for item in body["items"])


async def test_client_time_spent_by_category_route_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/clients/10.0.0.11/time-spent-by-category")
    assert response.status_code == 401
