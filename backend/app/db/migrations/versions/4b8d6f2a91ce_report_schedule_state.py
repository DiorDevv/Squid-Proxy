"""report schedule state

Revision ID: 4b8d6f2a91ce
Revises: 7c2e4a9f1d33
Create Date: 2026-07-19 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4b8d6f2a91ce'
down_revision: str | None = '7c2e4a9f1d33'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'report_schedule_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('report_schedule_state')
