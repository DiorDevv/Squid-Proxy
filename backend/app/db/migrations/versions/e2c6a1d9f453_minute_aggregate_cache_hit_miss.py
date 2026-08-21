"""minute aggregate cache hit/miss counters

Revision ID: e2c6a1d9f453
Revises: b3e9c7a2f1d4
Create Date: 2026-08-21 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2c6a1d9f453'
down_revision: str | None = 'b3e9c7a2f1d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfilled to 0, not left NULL: existing rows predate cache-hit
    # tracking and simply have no hit/miss data -- stats_service.
    # get_cache_efficiency treats hit_requests + miss_requests == 0 as "no
    # data for this window" (omits it) rather than dividing by zero or
    # showing a misleading 0% hit rate.
    op.add_column(
        'minute_aggregates', sa.Column('hit_requests', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'minute_aggregates', sa.Column('miss_requests', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('minute_aggregates', 'miss_requests')
    op.drop_column('minute_aggregates', 'hit_requests')
