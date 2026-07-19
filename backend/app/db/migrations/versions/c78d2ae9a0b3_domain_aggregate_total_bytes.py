"""domain aggregate total_bytes

Revision ID: c78d2ae9a0b3
Revises: c3dd467754e8
Create Date: 2026-07-18 22:20:45.878605

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c78d2ae9a0b3'
down_revision: str | None = 'c3dd467754e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default so existing rows (pre-dating this column) backfill to 0
    # instead of failing the NOT NULL constraint on non-empty tables.
    op.add_column(
        'domain_minute_aggregates',
        sa.Column('total_bytes', sa.BigInteger(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('domain_minute_aggregates', 'total_bytes')
