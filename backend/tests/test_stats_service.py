from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.models.minute_aggregate import MinuteAggregate
from app.schemas.common import Granularity, RangeParam
from app.services import domain_category_service
from app.services.stats_service import get_cache_efficiency, get_timeseries, get_top_domains


async def test_get_top_domains_orders_by_request_count(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="a.com", request_count=100, blocked_count=1),
            DomainMinuteAggregate(bucket_ts=bucket, domain="b.com", request_count=50, blocked_count=40),
        ]
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), limit=10, blocked_only=False
    )
    assert [item.domain for item in items] == ["a.com", "b.com"]


async def test_get_top_domains_filters_by_search_substring(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="example.com", request_count=100, blocked_count=0),
            DomainMinuteAggregate(bucket_ts=bucket, domain="other.net", request_count=50, blocked_count=0),
        ]
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session,
        RangeParam.ONE_HOUR.since(),
        datetime.now(UTC),
        limit=10,
        blocked_only=False,
        search="EXAMP",
    )
    assert [item.domain for item in items] == ["example.com"]


async def test_get_top_domains_search_is_case_insensitive_substring(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(DomainMinuteAggregate(bucket_ts=bucket, domain="mail.google.com", request_count=10, blocked_count=0))
    await db_session.commit()

    items = await get_top_domains(
        db_session,
        RangeParam.ONE_HOUR.since(),
        datetime.now(UTC),
        limit=10,
        blocked_only=False,
        search="GOOGLE",
    )
    assert [item.domain for item in items] == ["mail.google.com"]


async def test_get_top_domains_filters_by_inferred_category(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            # youtube.com infers as video_streaming (category_inference.py)
            DomainMinuteAggregate(bucket_ts=bucket, domain="youtube.com", request_count=100, blocked_count=0),
            DomainMinuteAggregate(bucket_ts=bucket, domain="github.com", request_count=50, blocked_count=0),
        ]
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session,
        RangeParam.ONE_HOUR.since(),
        datetime.now(UTC),
        limit=10,
        category=DomainCategoryLabel.VIDEO_STREAMING,
    )
    assert [item.domain for item in items] == ["youtube.com"]


async def test_get_top_domains_category_filter_respects_admin_override(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="youtube.com", request_count=100, blocked_count=0),
        ]
    )
    await domain_category_service.set_category(
        db_session, "youtube.com", DomainCategoryLabel.WORK_TOOLS, "actor-1"
    )
    await db_session.commit()

    video_items = await get_top_domains(
        db_session,
        RangeParam.ONE_HOUR.since(),
        datetime.now(UTC),
        limit=10,
        category=DomainCategoryLabel.VIDEO_STREAMING,
    )
    assert video_items == []

    work_items = await get_top_domains(
        db_session,
        RangeParam.ONE_HOUR.since(),
        datetime.now(UTC),
        limit=10,
        category=DomainCategoryLabel.WORK_TOOLS,
    )
    assert [item.domain for item in work_items] == ["youtube.com"]


async def test_get_top_domains_blocked_only_orders_by_blocked_count(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="a.com", request_count=100, blocked_count=1),
            DomainMinuteAggregate(bucket_ts=bucket, domain="b.com", request_count=50, blocked_count=40),
            DomainMinuteAggregate(bucket_ts=bucket, domain="c.com", request_count=10, blocked_count=0),
        ]
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), limit=10, blocked_only=True
    )
    # c.com has zero blocked hits and must be excluded (having blocked_total > 0).
    assert [item.domain for item in items] == ["b.com", "a.com"]


async def test_get_top_domains_respects_limit(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain=f"d{i}.com", request_count=i, blocked_count=0)
            for i in range(5)
        ]
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), limit=2, blocked_only=False
    )
    assert len(items) == 2


async def test_get_top_domains_excludes_out_of_range_buckets(db_session: AsyncSession):
    old_bucket = datetime.now(UTC) - timedelta(days=2)
    db_session.add(
        DomainMinuteAggregate(bucket_ts=old_bucket, domain="stale.com", request_count=999, blocked_count=0)
    )
    await db_session.commit()

    items = await get_top_domains(
        db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), limit=10, blocked_only=False
    )
    assert items == []


async def test_get_timeseries_minute_granularity_returns_raw_buckets(db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            MinuteAggregate(
                bucket_ts=now, total_requests=10, blocked_requests=1, allowed_requests=9, total_bytes=100
            ),
            MinuteAggregate(
                bucket_ts=now - timedelta(minutes=1),
                total_requests=5,
                blocked_requests=0,
                allowed_requests=5,
                total_bytes=50,
            ),
        ]
    )
    await db_session.commit()

    result = await get_timeseries(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), Granularity.MINUTE)
    assert len(result.points) == 2
    assert result.points[0].bucket_ts < result.points[1].bucket_ts


async def test_get_timeseries_hour_granularity_rebuckets(db_session: AsyncSession):
    hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    db_session.add_all(
        [
            MinuteAggregate(
                bucket_ts=hour, total_requests=10, blocked_requests=1, allowed_requests=9, total_bytes=100
            ),
            MinuteAggregate(
                bucket_ts=hour + timedelta(minutes=30),
                total_requests=20,
                blocked_requests=2,
                allowed_requests=18,
                total_bytes=200,
            ),
        ]
    )
    await db_session.commit()

    # `until` must cover both seeded buckets -- the second one is 30 minutes
    # *after* `hour`, which can be later than "now" if the test runs near
    # the top of an hour.
    result = await get_timeseries(
        db_session, RangeParam.TWENTY_FOUR_HOURS.since(), datetime.now(UTC) + timedelta(hours=1), Granularity.HOUR
    )
    assert len(result.points) == 1
    assert result.points[0].total_requests == 30
    assert result.points[0].blocked_requests == 3


async def test_top_domains_route_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/top-domains")
    assert response.status_code == 401


async def test_top_domains_route_returns_seeded_data(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(DomainMinuteAggregate(bucket_ts=bucket, domain="example.com", request_count=5, blocked_count=0))
    await db_session.commit()

    response = await app_client.get("/api/top-domains?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["domain"] == "example.com"


async def test_top_domains_route_filters_by_category_query_param(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="youtube.com", request_count=5, blocked_count=0),
            DomainMinuteAggregate(bucket_ts=bucket, domain="github.com", request_count=5, blocked_count=0),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/top-domains?range=1h&category=video_streaming", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["domain"] for item in body["items"]] == ["youtube.com"]


async def test_timeseries_route_returns_points(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=bucket, total_requests=1, blocked_requests=0, allowed_requests=1, total_bytes=10
        )
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/timeseries?range=1h&granularity=minute", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert len(response.json()["points"]) == 1


async def test_domain_search_route_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/domains/search?q=example")
    assert response.status_code == 401


async def test_domain_search_route_returns_matching_domains(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(bucket_ts=bucket, domain="example.com", request_count=5, blocked_count=0),
            DomainMinuteAggregate(bucket_ts=bucket, domain="unrelated.net", request_count=5, blocked_count=0),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/domains/search?q=exam&range=1h", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["domain"] for item in body["items"]] == ["example.com"]


async def test_domain_search_route_rejects_empty_query(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/domains/search?q=", headers=auth_headers(admin_token))
    assert response.status_code == 422


async def test_get_cache_efficiency_computes_hit_ratio(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=bucket,
            total_requests=10,
            blocked_requests=0,
            allowed_requests=10,
            hit_requests=3,
            miss_requests=7,
        )
    )
    await db_session.commit()

    result = await get_cache_efficiency(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC))
    assert result.hit_requests == 3
    assert result.miss_requests == 7
    assert result.hit_ratio == 0.3


async def test_get_cache_efficiency_ratio_is_none_when_nothing_cacheable(db_session: AsyncSession):
    """A window where every request was blocked or tunneled (hit + miss ==
    0) must report hit_ratio=None, not a misleading 0%."""
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=bucket, total_requests=5, blocked_requests=5, allowed_requests=0, hit_requests=0, miss_requests=0
        )
    )
    await db_session.commit()

    result = await get_cache_efficiency(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC))
    assert result.hit_ratio is None


async def test_cache_efficiency_route_returns_hit_ratio(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=bucket,
            total_requests=4,
            blocked_requests=0,
            allowed_requests=4,
            hit_requests=1,
            miss_requests=3,
        )
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/cache-efficiency?range=1h", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hit_requests"] == 1
    assert body["miss_requests"] == 3
    assert body["hit_ratio"] == 0.25


async def test_cache_efficiency_route_requires_auth(app_client: AsyncClient):
    response = await app_client.get("/api/cache-efficiency?range=1h")
    assert response.status_code == 401
