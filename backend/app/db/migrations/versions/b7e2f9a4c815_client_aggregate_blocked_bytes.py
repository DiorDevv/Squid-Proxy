"""client_minute_aggregates / client_hourly_aggregates blocked_bytes split

Revision ID: b7e2f9a4c815
Revises: a3f8c1d94b26
Create Date: 2026-09-16 14:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2f9a4c815"
down_revision: str | None = "a3f8c1d94b26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# total_bytes/bytes_received on these two tables already exclude blocked-
# request bytes (see a3f8c1d94b26's sibling change in aggregator.py --
# that migration only touched minute_aggregates, this one is the client-
# level follow-up). These new columns carry the excluded slice, so the
# "Kim" actor detail sheet can show blocked traffic as its own figure
# instead of it just disappearing from the Downloaded/Uploaded totals.
_TABLES = ("client_minute_aggregates", "client_hourly_aggregates")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("blocked_bytes", sa.BigInteger(), nullable=False, server_default="0")
        )
        op.add_column(
            table,
            sa.Column("blocked_bytes_received", sa.BigInteger(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "blocked_bytes_received")
        op.drop_column(table, "blocked_bytes")
