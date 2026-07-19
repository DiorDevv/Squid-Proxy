"""alert settings

Revision ID: 7c2e4a9f1d33
Revises: 1f6a9c3e5b21
Create Date: 2026-07-19 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c2e4a9f1d33'
down_revision: str | None = '1f6a9c3e5b21'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'alert_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sensitive_categories', sa.String(length=255), nullable=False),
        sa.Column('non_work_minutes_threshold', sa.Integer(), nullable=False),
        sa.Column('client_daily_byte_quota_bytes', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('alert_settings')
