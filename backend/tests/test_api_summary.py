from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate
from app.models.client_hourly_aggregate import ClientHourlyAggregate
from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.minute_aggregate import MinuteAggregate


async def _seed_minute(db_session: AsyncSession, minutes_ago: int, total: int, blocked: int) -> None:
    bucket = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=bucket, total_requests=total, blocked_requests=blocked, allowed_requests=total - blocked
        )
    )
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=bucket, client_ip="10.0.0.5", user="alice", request_count=total, blocked_count=blocked
        )
    )
    db_session.add(
        DomainMinuteAggregate(bucket_ts=bucket, domain="example.com", request_count=total, blocked_count=blocked)
    )
    await db_session.commit()


async def test_summary_reflects_seeded_aggregates(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_minute(db_session, minutes_ago=5, total=10, blocked=3)

    response = await app_client.get("/api/summary?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 10
    assert body["blocked_requests"] == 3
    assert body["allowed_requests"] == 7
    assert body["active_client_count"] == 1
    assert body["active_user_count"] == 1


async def test_summary_active_client_count_includes_rolled_up_hourly_clients(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    """A client whose old activity has already been compressed into
    client_hourly_aggregates (see retention.py) must still count as active
    for a wide enough range -- get_summary reads both tables combined."""
    now = datetime.now(UTC)
    old_hour = (now - timedelta(days=10)).replace(minute=0, second=0, microsecond=0)
    db_session.add(
        ClientHourlyAggregate(
            bucket_ts=old_hour, client_ip="10.0.0.20", user="erin", request_count=10, blocked_count=0, total_bytes=100
        )
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/summary",
        params={"from_ts": (now - timedelta(days=30)).isoformat(), "to_ts": now.isoformat()},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_client_count"] == 1
    assert body["active_user_count"] == 1


async def test_summary_excludes_data_outside_range(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    await _seed_minute(db_session, minutes_ago=200, total=50, blocked=10)  # outside 1h window

    response = await app_client.get("/api/summary?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 0


async def test_timeseries_returns_points(app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers):
    await _seed_minute(db_session, minutes_ago=1, total=5, blocked=1)

    response = await app_client.get("/api/timeseries?range=1h&granularity=minute", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body["points"]) == 1
    assert body["points"][0]["total_requests"] == 5


async def test_top_domains_and_top_blocked(app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers):
    await _seed_minute(db_session, minutes_ago=1, total=20, blocked=8)

    top_domains = await app_client.get("/api/top-domains?range=1h", headers=auth_headers(admin_token))
    assert top_domains.status_code == 200
    assert top_domains.json()["items"][0]["domain"] == "example.com"
    assert top_domains.json()["items"][0]["request_count"] == 20

    top_blocked = await app_client.get("/api/top-blocked?range=1h", headers=auth_headers(admin_token))
    assert top_blocked.status_code == 200
    assert top_blocked.json()["items"][0]["blocked_count"] == 8


async def test_health_endpoint_is_unauthenticated(app_client: AsyncClient):
    response = await app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
