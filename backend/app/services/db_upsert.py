"""Dialect-aware bulk "insert or increment" for the aggregate tables.

The aggregator used to select-then-increment one row at a time per distinct
(bucket, domain)/(bucket, client) key touched in a flush window -- one round
trip per key, sequentially, inside a single session. That's fine for a
handful of domains/clients per minute, but scales linearly with how many
distinct keys a flush window touches, which grows with traffic and client
count. A single `INSERT ... ON CONFLICT DO UPDATE` per table per flush does
the same "add to existing row, or create it" work in one statement.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Table
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

# A single INSERT's VALUES list binds len(row) * len(rows) parameters --
# SQLite's SQLITE_MAX_VARIABLE_NUMBER defaults to 999 on many still-common
# builds (raised to 32766 only on SQLite 3.32.0+ builds that also didn't
# lower it back down), and a flush window touching enough distinct
# buckets/domains/clients blows through either one if it all goes into one
# statement. Confirmed against a real ~500k-event burst (a single branch
# catching up after downtime): one flush's domain upsert hit "too many SQL
# variables" and got permanently stuck retrying the exact same
# still-too-large batch every interval, since nothing about a failed,
# uncommitted flush's pending events changes between retries. Chunking
# below keeps every dialect on one code path -- Postgres's own limit
# (65535) is high enough that this rarely bites there, but a second,
# sqlite-only branch would just be one more thing to keep in sync.
_MAX_VARIABLES_PER_STATEMENT = 900


async def bulk_upsert_sum(
    session: AsyncSession,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    index_elements: Sequence[ColumnElement | str],
    sum_columns: Sequence[str],
) -> None:
    """Insert every row in `rows`; for any that collide with an existing row
    on `index_elements`, add `sum_columns` to the existing values instead of
    overwriting them. `rows` must already be deduplicated on the conflict
    key (the aggregator's per-flush dict keys guarantee this) -- a multi-row
    VALUES list with two rows sharing a key is undefined per most dialects.

    `index_elements` may be plain columns/names for a normal unique index,
    or SQLAlchemy expressions (e.g. `func.coalesce(table.c.user, "")`) to
    match an expression-based unique index exactly, as
    client_minute_aggregates' (bucket_ts, client_ip, coalesce(user, '')))
    index requires.

    A big flush window's rows are split across as many statements as needed
    to stay under _MAX_VARIABLES_PER_STATEMENT -- all still inside the
    caller's single transaction (one commit after every table's upserts, see
    Aggregator.flush), so this doesn't change the "whole flush commits
    together or not at all" guarantee, it just avoids handing the driver one
    statement too large for it to run at all.
    """
    if not rows:
        return
    rows = list(rows)

    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert

    columns_per_row = len(rows[0])
    batch_size = max(1, _MAX_VARIABLES_PER_STATEMENT // columns_per_row)

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        stmt = insert(table).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(index_elements),
            set_={col: table.c[col] + stmt.excluded[col] for col in sum_columns},
        )
        await session.execute(stmt)
