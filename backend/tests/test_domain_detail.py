from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent


async def _visit(
    client_ip: str,
    domain: str,
    timestamp,
    user: str | None = None,
    blocked: bool = False,
    size: int = 100,
    branch: str = "default",
):
    return RawEvent(
        timestamp=timestamp,
        duration_ms=1,
        client_ip=client_ip,
        action="TCP_DENIED" if blocked else "TCP_MISS",
        status_code=403 if blocked else 200,
        bytes=size,
        method="GET",
        url=f"http://{domain}/",
        domain=domain,
        user=user,
        hierarchy=None,
        peer=None,
        content_type=None,
        blocked=blocked,
        branch=branch,
    )


async def test_domain_summary_rolls_up_all_clients(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now, size=100),
            await _visit("10.0.0.2", "example.com", now, size=200, blocked=True),
            await _visit("10.0.0.1", "other.com", now, size=999),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/domains/example.com/summary?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "example.com"
    assert body["total_requests"] == 2
    assert body["blocked_requests"] == 1
    assert body["total_bytes"] == 300
    assert body["distinct_client_count"] == 2
    assert body["category"] == "uncategorized"


async def test_domain_summary_shows_inferred_category(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add(await _visit("10.0.0.1", "youtube.com", now))
    await db_session.commit()

    response = await app_client.get("/api/domains/youtube.com/summary?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["category"] == "video_streaming"


async def test_domain_summary_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/domains/example.com/summary")
    assert response.status_code == 401


async def test_domain_clients_lists_one_row_per_client_sorted_by_visit_count(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now, user="alice"),
            await _visit("10.0.0.1", "example.com", now, user="alice"),
            await _visit("10.0.0.1", "example.com", now, user="alice"),
            await _visit("10.0.0.2", "example.com", now, user="bob"),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/domains/example.com/clients?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["client_ip"] == "10.0.0.1"
    assert body["items"][0]["visit_count"] == 3
    assert body["items"][0]["user"] == "alice"
    assert body["items"][1]["client_ip"] == "10.0.0.2"
    assert body["items"][1]["visit_count"] == 1


async def test_domain_clients_splits_rows_by_branch(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now, branch="tashkent"),
            await _visit("10.0.0.1", "example.com", now, branch="tashkent"),
            await _visit("10.0.0.1", "example.com", now, branch="samarqand"),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/domains/example.com/clients?range=1h&sort_by=visit_count", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    # Same IP, two branches -> two rows, not one rolled-up row.
    assert body["total"] == 2
    by_branch = {item["branch"]: item for item in body["items"]}
    assert by_branch["tashkent"]["visit_count"] == 2
    assert by_branch["samarqand"]["visit_count"] == 1


async def test_domain_clients_only_includes_visits_to_that_domain(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now),
            await _visit("10.0.0.1", "other.com", now),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/domains/example.com/clients?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1


async def test_domain_clients_respects_custom_time_range(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now - timedelta(days=10)),
            await _visit("10.0.0.2", "example.com", now),
        ]
    )
    await db_session.commit()

    response = await app_client.get("/api/domains/example.com/clients?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["client_ip"] == "10.0.0.2"


async def test_domain_clients_sorted_by_total_bytes(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now, size=50),
            await _visit("10.0.0.2", "example.com", now, size=5000),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/domains/example.com/clients?range=1h&sort_by=total_bytes&order=desc",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["client_ip"] == "10.0.0.2"


async def test_domain_clients_pagination(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            await _visit("10.0.0.1", "example.com", now),
            await _visit("10.0.0.2", "example.com", now),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/domains/example.com/clients?range=1h&limit=1&offset=1", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 2


async def test_domain_summary_with_no_traffic_returns_zeros(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/domains/never-visited.example/summary?range=1h", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 0
    assert body["distinct_client_count"] == 0
