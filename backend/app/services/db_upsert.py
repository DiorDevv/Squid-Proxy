"""Dialect-aware bulk "insert or increment" for the aggregate tables.

The aggregator used to select-then-increment one row at a time per distinct
(bucket, domain)/(bucket, client) key touched in a flush window -- one round
trip per key, sequentially, inside a single session. That's fine for a
handful of domains/clients per minute, but scales linearly with how many
distinct keys a flush window touches, which grows with traffic and client
count. A single `INSERT ... ON CONFLICT DO UPDATE` per table per flush does
the same "add to existing row, or create it" work in one statement.
"""

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.roles import DDLConstraintColumnRole


def declared_table(model: type[Any]) -> Table:
    """`model.__table__` narrowed to `Table`. SQLAlchemy's own stubs type a
    declarative class's `.__table__` as the more general `FromClause`
    (correct in the abstract -- a mapped class could in principle map to a
    join or subquery), but every model in this codebase maps directly to a
    `Table` via `__tablename__`, so this is a single, deliberate narrowing
    rather than a `# type: ignore` (or a `cast()`) repeated at every one of
    this module's callers."""
    return cast(Table, model.__table__)

# A single INSERT's VALUES list binds len(row) * len(rows) parameters --
# SQLite's SQLITE_MAX_VARIABLE_NUMBER defaults to 999 on many still-common
# builds (raised to 32766 only on SQLite 3.32.0+ builds that also didn't
# lower it back down), and a flush window touching enough distinct
# buckets/domains/clients blows through either one if it all goes into one
# statement. Confirmed against a real ~500k-event burst (a single branch
# catching up after downtime): one flush's domain upsert hit "too many SQL
# variables" and got permanently stuck retrying the exact same
# still-too-large batch every interval, since nothing about a failed,
# uncommitted flush's pending events changes between retries. This default
# keeps every dialect on one code path -- deliberately conservative
# (SQLite-safe) since bulk_upsert_sum's callers only ever deal in
# deduplicated per-key aggregate rows (at most one row per distinct
# bucket/domain/client touched in a window), never the raw per-event volume
# raw_events sees -- see _MAX_VARIABLES_PER_STATEMENT_POSTGRES below for why
# that path needs a dialect-aware, much larger batch instead of this one.
_MAX_VARIABLES_PER_STATEMENT = 900

# Postgres's real per-statement bound-parameter ceiling is 65535 -- far
# above SQLite's. Confirmed against a real ~750k-row raw_events insert
# (every event becomes its own row, no dedup, unlike the aggregate tables
# above): chunking at the SQLite-safe 900-variable size (60 rows/batch at
# raw_events' 15 columns) forced 12,500 round trips and took 130s, *slower*
# than one single unchunked statement's 91s -- round-trip overhead
# dominated at that granularity. This coarser, dialect-aware batch (2,000
# rows/batch at 15 columns) is what Aggregator.flush() uses for that
# insert instead.
_MAX_VARIABLES_PER_STATEMENT_POSTGRES = 30_000


def max_variables_for(session: AsyncSession) -> int:
    """The chunk_rows() budget to use for `session`'s dialect -- SQLite-safe
    by default, much larger for Postgres (see
    _MAX_VARIABLES_PER_STATEMENT_POSTGRES above)."""
    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "postgresql":
        return _MAX_VARIABLES_PER_STATEMENT_POSTGRES
    return _MAX_VARIABLES_PER_STATEMENT


def chunk_rows(
    rows: Sequence[Mapping[str, Any]],
    columns_per_row: int,
    max_variables: int = _MAX_VARIABLES_PER_STATEMENT,
) -> Iterator[Sequence[Mapping[str, Any]]]:
    """Splits `rows` into batches that stay under `max_variables` bound
    parameters per statement -- see this module's docstring/comments above
    for why. Shared by bulk_upsert_sum below (SQLite-safe default) and
    Aggregator.flush()'s plain raw_events insert (dialect-aware, via
    max_variables_for() above): several awaited round trips instead of one
    pathologically large statement also gives the event loop natural yield
    points between batches (still all inside the caller's one transaction --
    this changes how many statements it takes, not the commit boundary)."""
    batch_size = max(1, max_variables // columns_per_row)
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


async def bulk_upsert_sum(
    session: AsyncSession,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    index_elements: Sequence[DDLConstraintColumnRole | str],
    sum_columns: Sequence[str],
) -> None:
    """Insert every row in `rows`; for any that collide with an existing row
    on `index_elements`, add `sum_columns` to the existing values instead of
    overwriting them. `rows` must already be deduplicated on the conflict
    key (the aggregator's per-flush dict keys guarantee this) -- a multi-row
    VALUES list with two rows sharing a key is undefined per most dialects.

    `table` should be built via `declared_table()` above, not
    `Model.__table__` directly (see that function's docstring for why).

    `index_elements` may be plain columns (an `InstrumentedAttribute`, e.g.
    `Model.some_column`) or names for a normal unique index, or SQLAlchemy
    expressions (e.g. `func.coalesce(table.c.user, "")`) to match an
    expression-based unique index exactly, as client_minute_aggregates'
    (bucket_ts, client_ip, coalesce(user, '')) index requires.

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

    for batch in chunk_rows(rows, columns_per_row=len(rows[0])):
        stmt = insert(table).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(index_elements),
            set_={col: table.c[col] + stmt.excluded[col] for col in sum_columns},
        )
        await session.execute(stmt)
