"""alert settings and anomaly events become per-branch

Revision ID: b7e3d1a4c8f2
Revises: a4f7c2e9b1d6
Create Date: 2026-07-20 15:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e3d1a4c8f2'
down_revision: str | None = 'a4f7c2e9b1d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_BRANCH = 'default'


def upgrade() -> None:
    # alert_settings used to be a singleton row (id=1, one company-wide
    # policy); per-branch thresholds means the natural key is the branch
    # itself, not a surrogate id. There is at most one existing row in any
    # real install (the singleton), so this is a straightforward drop and
    # recreate rather than an in-place PK migration -- the one row of
    # config, if any, is not automatically re-attributable to a specific
    # branch and needs to be re-entered per branch via Settings after
    # upgrading (a one-time admin action, not data loss of traffic history).
    op.drop_table('alert_settings')
    op.create_table(
        'alert_settings',
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('sensitive_categories', sa.String(length=255), nullable=False),
        sa.Column('non_work_minutes_threshold', sa.Integer(), nullable=False),
        sa.Column('client_daily_byte_quota_bytes', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('branch'),
    )

    op.add_column(
        'anomaly_events',
        sa.Column('branch', sa.String(length=64), nullable=False, server_default=_DEFAULT_BRANCH),
    )
    op.create_index('ix_anomaly_events_branch', 'anomaly_events', ['branch'])


def downgrade() -> None:
    op.drop_index('ix_anomaly_events_branch', table_name='anomaly_events')
    op.drop_column('anomaly_events', 'branch')

    op.drop_table('alert_settings')
    op.create_table(
        'alert_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sensitive_categories', sa.String(length=255), nullable=False),
        sa.Column('non_work_minutes_threshold', sa.Integer(), nullable=False),
        sa.Column('client_daily_byte_quota_bytes', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
