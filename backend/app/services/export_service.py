"""CSV/JSON export of raw events for a time range. Admin-only (see api/routes/export.py)."""

import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import db as db_module
from app.models.raw_event import RawEvent
from app.services.event_query_service import build_event_conditions

_COLUMNS = [
    "id",
    "timestamp",
    "client_ip",
    "branch",
    "user",
    "method",
    "url",
    "domain",
    "action",
    "status_code",
    "bytes",
    "blocked",
]

EXPORT_ROW_LIMIT = 100_000

# Columns that can carry attacker-influenced text (from Squid log lines) and
# so need CSV formula-injection escaping before being opened in a spreadsheet.
_FORMULA_RISK_COLUMNS = {"client_ip", "user", "url", "domain"}
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _escape_csv_formula(value: object) -> object:
    """Neutralize CSV/Excel formula injection (leading =, +, -, @, tab, CR).

    Excel/Sheets treat a cell as a formula if it starts with one of these
    characters, regardless of column type; prefixing with a single quote
    forces it to be read back as literal text.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return f"'{value}"
    return value


async def _fetch_rows(
    session: AsyncSession, since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> list[RawEvent]:
    conditions = build_event_conditions(since, until, blocked_only=blocked_only, branch=branch)

    query = (
        select(RawEvent)
        .where(*conditions)
        .order_by(RawEvent.timestamp.desc())
        .limit(EXPORT_ROW_LIMIT)
    )
    return (await session.execute(query)).scalars().all()


def _row_to_dict(row: RawEvent) -> dict:
    return {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if isinstance(row.timestamp, datetime) else row.timestamp,
        "client_ip": row.client_ip,
        "branch": row.branch,
        "user": row.user,
        "method": row.method,
        "url": row.url,
        "domain": row.domain,
        "action": row.action,
        "status_code": row.status_code,
        "bytes": row.bytes,
        "blocked": row.blocked,
    }


async def export_as_csv(
    session: AsyncSession, since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> str:
    rows = await _fetch_rows(session, since, until, blocked_only, branch)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_COLUMNS)
    writer.writeheader()
    for row in rows:
        record = _row_to_dict(row)
        for column in _FORMULA_RISK_COLUMNS:
            record[column] = _escape_csv_formula(record[column])
        writer.writerow(record)
    return buffer.getvalue()


async def export_as_json(
    session: AsyncSession, since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> str:
    rows = await _fetch_rows(session, since, until, blocked_only, branch)
    return json.dumps([_row_to_dict(row) for row in rows])


# --- Streaming, uncapped variants ---
#
# The two functions above are for report_service.py's emailed CSV attachment
# (EXPORT_ROW_LIMIT and an in-memory string are both fine there -- nobody
# wants a multi-hundred-MB email attachment anyway). GET /api/export and
# scripts/archive_weekly_export.py need the opposite: the *complete* range
# even when that's millions of rows (a real deployment's raw_events table
# holds that much for even a single day), without ever holding the whole
# thing in memory at once. Keyset pagination (by id, not OFFSET) keeps every
# query O(batch size) regardless of how far into the range it is.

_STREAM_BATCH_SIZE = 5_000


async def _iter_batches(
    session: AsyncSession, since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> AsyncIterator[list[RawEvent]]:
    conditions = build_event_conditions(since, until, blocked_only=blocked_only, branch=branch)
    last_id = 0
    while True:
        query = (
            select(RawEvent)
            .where(*conditions, RawEvent.id > last_id)
            .order_by(RawEvent.id)
            .limit(_STREAM_BATCH_SIZE)
        )
        rows = (await session.execute(query)).scalars().all()
        if not rows:
            return
        yield rows
        last_id = rows[-1].id
        if len(rows) < _STREAM_BATCH_SIZE:
            return


async def stream_csv(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    blocked_only: bool,
    branch: str | None = None,
    row_counter: list[int] | None = None,
) -> AsyncIterator[str]:
    """row_counter, if given, is incremented (as a one-element out-param --
    an async generator can't return a value alongside its yields) by the
    number of rows in every batch actually written. export_job_service.run_job
    uses this instead of a separate COUNT(*) after the fact: since/until are
    a fixed range but this table keeps getting new matching rows inserted in
    real time, a follow-up count query can (and, under real traffic, will)
    see rows that arrived after streaming already finished, so it doesn't
    reliably describe what ended up in the file."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_COLUMNS)
    writer.writeheader()
    yield buffer.getvalue()

    async for batch in _iter_batches(session, since, until, blocked_only, branch):
        if row_counter is not None:
            row_counter[0] += len(batch)
        buffer.seek(0)
        buffer.truncate(0)
        for row in batch:
            record = _row_to_dict(row)
            for column in _FORMULA_RISK_COLUMNS:
                record[column] = _escape_csv_formula(record[column])
            writer.writerow(record)
        yield buffer.getvalue()


async def stream_json(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    blocked_only: bool,
    branch: str | None = None,
    row_counter: list[int] | None = None,
) -> AsyncIterator[str]:
    """See stream_csv's docstring for row_counter."""
    yield "["
    first = True
    async for batch in _iter_batches(session, since, until, blocked_only, branch):
        if row_counter is not None:
            row_counter[0] += len(batch)
        parts = []
        for row in batch:
            parts.append(("" if first else ",") + json.dumps(_row_to_dict(row)))
            first = False
        yield "".join(parts)
    yield "]"


async def download_csv(
    since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> AsyncIterator[str]:
    """Route-facing entry point for GET /api/export: opens and holds its own
    session for the whole streaming duration.

    A FastAPI `Depends(get_db)` session is the wrong tool here -- its
    cleanup runs right after the endpoint returns the StreamingResponse
    object, *before* Starlette actually pulls this generator to send the
    body, so a request-injected session would already be closed by the time
    any of the query above ran. Opening a fresh session inside the
    generator itself sidesteps that entirely.
    """
    async with db_module.AsyncSessionLocal() as session:
        async for chunk in stream_csv(session, since, until, blocked_only, branch):
            yield chunk


async def download_json(
    since: datetime, until: datetime, blocked_only: bool, branch: str | None = None
) -> AsyncIterator[str]:
    """download_csv's JSON counterpart -- see its docstring for why this
    owns its own session instead of taking one via FastAPI's DI."""
    async with db_module.AsyncSessionLocal() as session:
        async for chunk in stream_json(session, since, until, blocked_only, branch):
            yield chunk
