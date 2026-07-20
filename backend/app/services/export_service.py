"""CSV/JSON export of raw events for a time range. Admin-only (see api/routes/export.py)."""

import csv
import io
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
