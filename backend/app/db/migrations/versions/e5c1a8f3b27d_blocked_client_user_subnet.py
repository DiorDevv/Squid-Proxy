"""Blocked-domain client aggregate: login and /24 subnet dimensions

Revision ID: e5c1a8f3b27d
Revises: b2d7f4a9c1e3
Create Date: 2026-10-13 13:00:00.000000

`user` joins the unique key, so existing rows (all written without it) are
cleared rather than guessed at -- refill with
scripts/backfill_blocked_domains.py.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5c1a8f3b27d"
down_revision: str | None = "b2d7f4a9c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "blocked_domain_client_hourly_aggregates"
_KEY = "ix_blocked_domain_client_hourly_key"


def upgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE}")  # noqa: S608
    op.drop_index(_KEY, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("user", sa.String(length=255), nullable=False, server_default=""))
        batch.add_column(sa.Column("subnet", sa.String(length=45), nullable=False, server_default=""))
    op.create_index(
        _KEY, _TABLE, ["bucket_ts", "branch", "proxy", "domain", "client_ip", "user"], unique=True
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE}")  # noqa: S608
    op.drop_index(_KEY, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("subnet")
        batch.drop_column("user")
    op.create_index(_KEY, _TABLE, ["bucket_ts", "branch", "proxy", "domain", "client_ip"], unique=True)
