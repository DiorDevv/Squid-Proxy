"""bytes_received (%>st, upload) on raw_events + the byte-carrying aggregates

Revision ID: f2a7c4e9b183
Revises: e1c8a3f7d24b
Create Date: 2026-09-09 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7c4e9b183"
down_revision: str | None = "e1c8a3f7d24b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# raw_events keeps it nullable: a log line with only %<st has no upload value
# to record, and NULL there must stay distinct from "uploaded 0 bytes". The
# aggregates always hold a number, defaulting to 0, so a mixed period (some
# branches on the two-size logformat, some not) still sums cleanly.
_AGGREGATE_TABLES = (
    "minute_aggregates",
    "client_minute_aggregates",
    "client_hourly_aggregates",
    "domain_minute_aggregates",
)


def upgrade() -> None:
    op.add_column("raw_events", sa.Column("bytes_received", sa.BigInteger(), nullable=True))
    for table in _AGGREGATE_TABLES:
        # server_default so rows predating the column backfill to 0 instead
        # of failing NOT NULL on a non-empty table (same pattern as
        # c78d2ae9a0b3 for total_bytes); left in place afterwards.
        op.add_column(
            table,
            sa.Column("bytes_received", sa.BigInteger(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for table in _AGGREGATE_TABLES:
        op.drop_column(table, "bytes_received")
    op.drop_column("raw_events", "bytes_received")
