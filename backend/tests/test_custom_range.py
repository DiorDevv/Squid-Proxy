"""Tests for the shared custom-date-range resolution (app/schemas/common.py:
resolve_range), used by /api/summary, /api/timeseries, /api/top-domains,
/api/clients, and /api/export."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.minute_aggregate import MinuteAggregate
from app.schemas.common import RangeParam, resolve_range


def test_resolve_range_defaults_to_24h_preset_when_nothing_given():
    effective = resolve_range(range=None, from_ts=None, to_ts=None)
    assert effective.range == RangeParam.TWENTY_FOUR_HOURS


def test_resolve_range_uses_explicit_preset():
    effective = resolve_range(range=RangeParam.ONE_HOUR, from_ts=None, to_ts=None)
    assert effective.range == RangeParam.ONE_HOUR


def test_resolve_range_accepts_a_valid_custom_window():
    now = datetime.now(UTC)
    effective = resolve_range(range=None, from_ts=now - timedelta(hours=3), to_ts=now)
    assert effective.range is None
    assert effective.since == now - timedelta(hours=3)
    assert effective.until == now


def test_resolve_range_rejects_from_ts_without_to_ts():
    with pytest.raises(HTTPException) as exc_info:
        resolve_range(range=None, from_ts=datetime.now(UTC), to_ts=None)
    assert exc_info.value.status_code == 400


def test_resolve_range_rejects_from_ts_after_to_ts():
    now = datetime.now(UTC)
    with pytest.raises(HTTPException) as exc_info:
        resolve_range(range=None, from_ts=now, to_ts=now - timedelta(hours=1))
    assert exc_info.value.status_code == 400


def test_resolve_range_treats_naive_datetimes_as_utc():
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    effective = resolve_range(range=None, from_ts=now_naive - timedelta(hours=1), to_ts=now_naive)
    assert effective.since.tzinfo is not None
    assert effective.until.tzinfo is not None


async def test_summary_route_honors_custom_range(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    in_range_bucket = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    out_of_range_bucket = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    db_session.add_all(
        [
            MinuteAggregate(
                bucket_ts=in_range_bucket, total_requests=10, blocked_requests=1, allowed_requests=9, total_bytes=100
            ),
            MinuteAggregate(
                bucket_ts=out_of_range_bucket,
                total_requests=999,
                blocked_requests=0,
                allowed_requests=999,
                total_bytes=9999,
            ),
        ]
    )
    await db_session.commit()

    response = await app_client.get(
        "/api/summary?from_ts=2026-01-15T00:00:00Z&to_ts=2026-01-16T00:00:00Z",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["range"] is None
    assert body["total_requests"] == 10


async def test_summary_route_rejects_malformed_custom_range(
    app_client: AsyncClient, admin_token, auth_headers
):
    response = await app_client.get(
        "/api/summary?from_ts=2026-01-16T00:00:00Z&to_ts=2026-01-15T00:00:00Z",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 400
