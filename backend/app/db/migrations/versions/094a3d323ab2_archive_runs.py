"""archive runs

Revision ID: 094a3d323ab2
Revises: 3d8f5a2c9e14
Create Date: 2026-07-21 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '094a3d323ab2'
down_revision: str | None = '3d8f5a2c9e14'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'archive_runs',
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('archived_until', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('branch'),
    )


def downgrade() -> None:
    op.drop_table('archive_runs')
