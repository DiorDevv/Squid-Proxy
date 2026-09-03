"""raw_events: widen bytes/duration_ms to BIGINT

A single large download (OS/browser update, video) logs a %<st byte count
past the int32 ceiling (~2,147,483,647), and a long-lived CONNECT tunnel's
%tr can do the same. On Postgres that value overflows an INTEGER column and
asyncpg raises DataError for the whole executemany() batch; the aggregator
never advances past an uncommitted flush, so it retries the same poisoned
batch every interval and the unflushed backlog grows until the ring buffer
overflows and events are dropped without ever being persisted.

Every aggregate table's total_bytes is already BigInteger (see
c78d2ae9a0b3); this brings raw_events into line.

SQLite is dev/test only there and builds its schema from the models via
create_all (not this migration), and its INTEGER storage class is already
64-bit -- so the ALTERs are Postgres-only.

Revision ID: c1e7a4b9d2f6
Revises: b7e05e34cae1
Create Date: 2026-09-03 18:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1e7a4b9d2f6'
down_revision: str | None = 'b7e05e34cae1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _retype(column: str, from_: sa.types.TypeEngine, to: sa.types.TypeEngine) -> None:
    op.alter_column(
        "raw_events",
        column,
        existing_type=from_,
        type_=to,
        existing_nullable=False,
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _retype("bytes", sa.Integer(), sa.BigInteger())
    _retype("duration_ms", sa.Integer(), sa.BigInteger())


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # No USING clause: a row that still fits in int32 casts back cleanly,
    # and one that doesn't should block the downgrade rather than be
    # silently truncated.
    _retype("bytes", sa.BigInteger(), sa.Integer())
    _retype("duration_ms", sa.BigInteger(), sa.Integer())
