import csv
import io
import json
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
from app.schemas.common import RangeParam
from app.services.export_service import (
    EXPORT_ROW_LIMIT,
    export_as_csv,
    export_as_json,
    stream_csv,
    stream_json,
)


def _make_event(**overrides) -> RawEvent:
    defaults = dict(
        timestamp=datetime.now(UTC),
        duration_ms=1,
        client_ip="10.0.0.1",
        action="TCP_MISS",
        status_code=200,
        bytes=100,
        method="GET",
        url="http://example.com/",
        domain="example.com",
        user="alice",
        hierarchy="HIER_DIRECT",
        peer=None,
        content_type="text/html",
        blocked=False,
    )
    defaults.update(overrides)
    return RawEvent(**defaults)


async def test_export_as_csv_escapes_formula_injection(db_session: AsyncSession):
    db_session.add_all(
        [
            _make_event(client_ip="10.0.0.1", domain="=cmd|'/c calc'!A1", url="+HYPERLINK(\"http://evil\")"),
            _make_event(client_ip="10.0.0.2", user="@SUM(1+1)"),
        ]
    )
    await db_session.commit()

    csv_body = await export_as_csv(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False)
    reader = csv.DictReader(io.StringIO(csv_body))
    rows_by_ip = {row["client_ip"]: row for row in reader}

    assert rows_by_ip["10.0.0.1"]["domain"].startswith("'=")
    assert rows_by_ip["10.0.0.1"]["url"].startswith("'+")
    assert rows_by_ip["10.0.0.2"]["user"].startswith("'@")
    # Safe values are left untouched.
    assert rows_by_ip["10.0.0.2"]["client_ip"] == "10.0.0.2"


async def test_export_as_json_does_not_mangle_values(db_session: AsyncSession):
    db_session.add(_make_event(domain="=evil.com"))
    await db_session.commit()

    body = await export_as_json(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False)
    parsed = json.loads(body)

    # JSON isn't opened in a spreadsheet, so it shouldn't be quote-prefixed.
    assert parsed[0]["domain"] == "=evil.com"


async def test_export_respects_blocked_only_filter(db_session: AsyncSession):
    db_session.add_all(
        [
            _make_event(client_ip="10.0.0.1", blocked=False),
            _make_event(client_ip="10.0.0.2", blocked=True, action="TCP_DENIED", status_code=403),
        ]
    )
    await db_session.commit()

    csv_body = await export_as_csv(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=True)
    reader = csv.DictReader(io.StringIO(csv_body))
    rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["client_ip"] == "10.0.0.2"


async def test_export_row_count_is_capped(db_session: AsyncSession, monkeypatch):
    import app.services.export_service as export_service_module

    monkeypatch.setattr(export_service_module, "EXPORT_ROW_LIMIT", 3)
    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(10)])
    await db_session.commit()

    csv_body = await export_as_csv(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False)
    reader = csv.DictReader(io.StringIO(csv_body))
    assert len(list(reader)) == 3
    # The real constant is untouched by the monkeypatch above.
    assert EXPORT_ROW_LIMIT == 100_000


async def test_stream_csv_is_not_row_limited(db_session: AsyncSession, monkeypatch):
    # Force many small batches (instead of one query returning everything)
    # to prove pagination across batch boundaries doesn't drop or duplicate
    # rows, and that -- unlike export_as_csv -- this never consults
    # EXPORT_ROW_LIMIT at all. GET /api/export and
    # scripts/archive_weekly_export.py both rely on this for ranges far
    # past that cap (a real deployment's raw_events table holds millions of
    # rows for even a single day).
    import app.services.export_service as export_service_module

    monkeypatch.setattr(export_service_module, "_STREAM_BATCH_SIZE", 3)
    row_total = 250
    db_session.add_all([_make_event(client_ip=f"10.0.{i // 250}.{i % 250}") for i in range(row_total)])
    await db_session.commit()

    chunks = [
        chunk
        async for chunk in stream_csv(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False)
    ]
    csv_body = "".join(chunks)
    reader = csv.DictReader(io.StringIO(csv_body))
    assert len(list(reader)) == row_total


async def test_stream_csv_escapes_formula_injection(db_session: AsyncSession):
    db_session.add(_make_event(client_ip="10.0.0.1", domain="=cmd|'/c calc'!A1"))
    await db_session.commit()

    chunks = [
        chunk
        async for chunk in stream_csv(db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False)
    ]
    reader = csv.DictReader(io.StringIO("".join(chunks)))
    assert next(reader)["domain"].startswith("'=")


async def test_stream_json_produces_valid_json_across_batches(db_session: AsyncSession, monkeypatch):
    import app.services.export_service as export_service_module

    monkeypatch.setattr(export_service_module, "_STREAM_BATCH_SIZE", 2)
    db_session.add_all([_make_event(client_ip=f"10.0.0.{i}") for i in range(7)])
    await db_session.commit()

    chunks = [
        chunk
        async for chunk in stream_json(
            db_session, RangeParam.ONE_HOUR.since(), datetime.now(UTC), blocked_only=False
        )
    ]
    parsed = json.loads("".join(chunks))
    assert len(parsed) == 7


async def test_export_route_returns_csv_with_headers(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/export?format=csv", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]


async def test_export_route_returns_json(app_client: AsyncClient, admin_token, auth_headers):
    response = await app_client.get("/api/export?format=json", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert json.loads(response.text) == []
