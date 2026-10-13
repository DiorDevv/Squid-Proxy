"""raw_events / client aggregates proxy column

Revision ID: c4d8e1f7a392
Revises: b7e2f9a4c815
Create Date: 2026-10-13 07:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8e1f7a392"
down_revision: str | None = "b7e2f9a4c815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# LogSource.proxy -- which proxy of a branch fed by several (a parent plus
# its child proxies) a request went through. Nullable with no default, so
# on Postgres each add_column is a metadata-only change even on the large
# raw_events table.
_AGGREGATE_TABLES = ("client_minute_aggregates", "client_hourly_aggregates")


def upgrade() -> None:
    op.add_column("raw_events", sa.Column("proxy", sa.String(length=64), nullable=True))
    for table in _AGGREGATE_TABLES:
        op.add_column(table, sa.Column("proxy", sa.String(length=255), nullable=True))


def downgrade() -> None:
    for table in _AGGREGATE_TABLES:
        op.drop_column(table, "proxy")
    op.drop_column("raw_events", "proxy")
