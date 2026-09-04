"""Tests for app/api/routes/analytics.py."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.minute_aggregate import MinuteAggregate

ENDPOINTS = [
    "/api/analytics/overview",
    "/api/analytics/category-trend",
    "/api/analytics/branch-breakdown",
    "/api/analytics/branch-risk",
    "/api/analytics/activity-heatmap",
]


async def test_analytics_endpoints_require_auth(app_client: AsyncClient):
    for path in ENDPOINTS:
        response = await app_client.get(path)
        assert response.status_code == 401, path


async def test_analytics_endpoints_allow_viewer(app_client: AsyncClient, viewer_token, auth_headers):
    for path in ENDPOINTS:
        response = await app_client.get(path, headers=auth_headers(viewer_token))
        assert response.status_code == 200, f"{path}: {response.text}"


async def test_overview_shape(app_client: AsyncClient, admin_token, auth_headers, db_session: AsyncSession):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        MinuteAggregate(
            bucket_ts=now - timedelta(minutes=5),
            total_requests=10,
            blocked_requests=2,
            allowed_requests=8,
            total_bytes=500,
        )
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/analytics/overview", params={"range": "24h"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert {m["metric"] for m in body["metrics"]} >= {
        "total_requests",
        "blocked_requests",
        "blocked_ratio",
        "cache_hit_ratio",
    }
    assert "top_categories" in body and "top_blocked_domains" in body


async def test_branch_scoped_admin_only_sees_own_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers, db_session: AsyncSession
):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add_all(
        [
            MinuteAggregate(bucket_ts=now - timedelta(minutes=1), branch="branch-a", total_requests=5, allowed_requests=5),
            MinuteAggregate(bucket_ts=now - timedelta(minutes=1), branch="branch-b", total_requests=999, allowed_requests=999),
        ]
    )
    await db_session.commit()

    breakdown = await app_client.get(
        "/api/analytics/branch-breakdown", headers=auth_headers(branch_a_admin_token)
    )
    assert breakdown.status_code == 200
    rows = breakdown.json()["rows"]
    assert [r["branch"] for r in rows] == ["branch-a"]

    risk = await app_client.get(
        "/api/analytics/branch-risk", headers=auth_headers(branch_a_admin_token)
    )
    assert [r["branch"] for r in risk.json()["rows"]] == ["branch-a"]


async def test_branch_scoped_admin_cannot_request_other_branch(
    app_client: AsyncClient, branch_a_admin_token, auth_headers
):
    response = await app_client.get(
        "/api/analytics/overview",
        params={"branch": "branch-b"},
        headers=auth_headers(branch_a_admin_token),
    )
    assert response.status_code == 403


async def test_category_trend_accepts_day_granularity_and_requests_metric(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/analytics/category-trend",
        params={"range": "7d", "granularity": "day", "metric": "requests"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["granularity"] == "day"
    assert body["metric"] == "requests"


async def test_activity_heatmap_echoes_tz_offset_and_bounds_it(
    app_client: AsyncClient, admin_token, auth_headers
):
    ok = await app_client.get(
        "/api/analytics/activity-heatmap",
        params={"range": "7d", "tz_offset_minutes": 300},
        headers=auth_headers(admin_token),
    )
    assert ok.status_code == 200
    assert ok.json()["tz_offset_minutes"] == 300

    out_of_range = await app_client.get(
        "/api/analytics/activity-heatmap",
        params={"range": "7d", "tz_offset_minutes": 5000},
        headers=auth_headers(admin_token),
    )
    assert out_of_range.status_code == 422
