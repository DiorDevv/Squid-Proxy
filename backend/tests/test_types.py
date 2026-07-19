"""Regression tests for UTCDateTime (app/models/types.py).

Real bug this guards against: SQLite drops tzinfo on a round-tripped
`DateTime(timezone=True)` value, so a naive datetime came back out of the
DB even though it was written as UTC. FastAPI/Pydantic then serialized it
without a `Z`/`+00:00` suffix, and every browser's `new Date(...)` parsed
that as *local* time -- shifting every "X ago" display by the viewer's UTC
offset (a client active seconds ago showed as "5h ago" for a UTC+5 viewer).
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_aggregate import ClientMinuteAggregate


async def test_bucket_ts_round_trips_as_utc_aware(db_session: AsyncSession):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        ClientMinuteAggregate(bucket_ts=bucket, client_ip="10.0.0.1", user=None, request_count=1, blocked_count=0)
    )
    await db_session.commit()
    db_session.expire_all()

    row = (await db_session.execute(select(ClientMinuteAggregate))).scalar_one()

    assert row.bucket_ts.tzinfo is not None
    assert row.bucket_ts == bucket


async def test_client_last_activity_serializes_with_utc_offset(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    bucket = datetime.now(UTC).replace(second=0, microsecond=0)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=bucket, client_ip="10.0.0.2", user="alice", request_count=1, blocked_count=0
        )
    )
    await db_session.commit()

    response = await app_client.get("/api/clients?range=1h", headers=auth_headers(admin_token))
    assert response.status_code == 200
    last_activity = response.json()["items"][0]["last_activity"]

    # A timezone-less string here is exactly the bug: browsers parse it as
    # local time, not UTC, silently shifting every relative timestamp.
    assert last_activity.endswith("+00:00") or last_activity.endswith("Z")

    parsed = datetime.fromisoformat(last_activity)
    assert abs((parsed - bucket).total_seconds()) < 1


async def test_response_last_activity_is_not_hours_off_from_now(
    app_client: AsyncClient, db_session: AsyncSession, admin_token, auth_headers
):
    """End-to-end guard: a client active *right now* must not appear to be
    hours in the past once the timestamp round-trips through the DB and
    back out over the API."""
    now = datetime.now(UTC).replace(microsecond=0)
    db_session.add(
        ClientMinuteAggregate(
            bucket_ts=now, client_ip="10.0.0.3", user="bob", request_count=1, blocked_count=0
        )
    )
    await db_session.commit()

    response = await app_client.get("/api/clients?range=1h", headers=auth_headers(admin_token))
    body = response.json()
    last_activity = datetime.fromisoformat(body["items"][0]["last_activity"])

    assert abs((datetime.now(UTC) - last_activity).total_seconds()) < timedelta(minutes=1).total_seconds()
