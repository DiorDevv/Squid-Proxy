"""Tests for domain category assignment (app/services/domain_category_service.py)
and the by-category usage rollup (app/services/stats_service.get_usage_by_category)
-- the latter is a regression test for a real bug: SQLAlchemy's Enum type
persists/reads a Python enum's *name* ("UNCATEGORIZED"), not its `.value`
("uncategorized"), so the coalesce fallback for domains with no assigned
category must match that or every query raises a LookupError."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_aggregate import DomainMinuteAggregate
from app.models.domain_category import DomainCategoryLabel
from app.services import domain_category_service
from app.services.stats_service import get_usage_by_category


async def test_set_category_creates_then_updates(db_session: AsyncSession):
    created = await domain_category_service.set_category(
        db_session, "example.com", DomainCategoryLabel.SOCIAL_MEDIA
    )
    assert created.category == DomainCategoryLabel.SOCIAL_MEDIA

    updated = await domain_category_service.set_category(
        db_session, "example.com", DomainCategoryLabel.WORK_TOOLS
    )
    assert updated.category == DomainCategoryLabel.WORK_TOOLS

    all_rows = await domain_category_service.list_all(db_session)
    assert len(all_rows) == 1
    assert all_rows[0].category == DomainCategoryLabel.WORK_TOOLS


async def test_usage_by_category_groups_uncategorized_domains_without_error(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="no-category.com", request_count=10, blocked_count=0, total_bytes=100
            ),
        ]
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = await get_usage_by_category(db_session, since, until)

    assert len(items) == 1
    assert items[0].category == DomainCategoryLabel.UNCATEGORIZED
    assert items[0].request_count == 10
    assert items[0].total_bytes == 100


async def test_usage_by_category_splits_categorized_and_uncategorized(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="social.example", request_count=5, blocked_count=0, total_bytes=50
            ),
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="mystery.example", request_count=3, blocked_count=0, total_bytes=30
            ),
        ]
    )
    await domain_category_service.set_category(db_session, "social.example", DomainCategoryLabel.SOCIAL_MEDIA)
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert items[DomainCategoryLabel.SOCIAL_MEDIA].request_count == 5
    assert items[DomainCategoryLabel.UNCATEGORIZED].request_count == 3


async def test_usage_by_category_falls_back_to_inferred_category(db_session: AsyncSession):
    """A domain nobody has explicitly categorized still lands somewhere
    useful (not a flat "uncategorized" bucket) via category_inference.py --
    e.g. a known video site's traffic shows up under video_streaming with
    zero admin effort."""
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="youtube.com", request_count=7, blocked_count=0, total_bytes=700
            ),
        ]
    )
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert DomainCategoryLabel.VIDEO_STREAMING in items
    assert items[DomainCategoryLabel.VIDEO_STREAMING].request_count == 7


async def test_usage_by_category_admin_override_wins_over_inference(db_session: AsyncSession):
    """youtube.com would infer as video_streaming -- an explicit admin
    override must still take precedence."""
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            DomainMinuteAggregate(
                bucket_ts=bucket, domain="youtube.com", request_count=4, blocked_count=0, total_bytes=400
            ),
        ]
    )
    await domain_category_service.set_category(db_session, "youtube.com", DomainCategoryLabel.WORK_TOOLS)
    await db_session.commit()

    since = bucket - timedelta(hours=1)
    until = bucket + timedelta(hours=1)
    items = {item.category: item for item in await get_usage_by_category(db_session, since, until)}

    assert DomainCategoryLabel.WORK_TOOLS in items
    assert DomainCategoryLabel.VIDEO_STREAMING not in items


async def test_domain_categories_route_requires_admin(app_client: AsyncClient, viewer_token, auth_headers):
    response = await app_client.get("/api/domain-categories", headers=auth_headers(viewer_token))
    assert response.status_code == 403


async def test_set_and_list_domain_category_via_api(app_client: AsyncClient, admin_token, auth_headers):
    put_response = await app_client.put(
        "/api/domain-categories/video.example",
        headers=auth_headers(admin_token),
        json={"category": "video_streaming"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["category"] == "video_streaming"

    list_response = await app_client.get("/api/domain-categories", headers=auth_headers(admin_token))
    assert list_response.status_code == 200
    domains = {row["domain"]: row["category"] for row in list_response.json()}
    assert domains["video.example"] == "video_streaming"
