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
    """
    if not rows:
        return

    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert

    stmt = insert(table).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=list(index_elements),
        set_={col: table.c[col] + stmt.excluded[col] for col in sum_columns},
    )
    await session.execute(stmt)
