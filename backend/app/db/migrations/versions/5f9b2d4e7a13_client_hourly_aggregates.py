"""client_hourly_aggregates

Revision ID: 5f9b2d4e7a13
Revises: 2e7c4a1f803d
Create Date: 2026-07-19 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5f9b2d4e7a13'
down_revision: str | None = '2e7c4a1f803d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNIQUE_INDEX = 'ix_client_hourly_bucket_ip_user_unique'


def upgrade() -> None:
    op.create_table(
        'client_hourly_aggregates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('client_ip', sa.String(length=45), nullable=False),
        sa.Column('user', sa.String(length=255), nullable=True),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('blocked_count', sa.Integer(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_client_hourly_aggregates_bucket_ts', 'client_hourly_aggregates', ['bucket_ts'])
    op.create_index('ix_client_hourly_aggregates_client_ip', 'client_hourly_aggregates', ['client_ip'])
    op.create_index('ix_client_hourly_aggregates_user', 'client_hourly_aggregates', ['user'])
    # No plain (bucket_ts, client_ip) index here -- the unique index created
    # below already leads with those same two columns, so a separate index
    # would only add write/storage cost with no query benefit.
    # Same nullable-`user` distinctness problem as client_minute_aggregates
    # (see migration 466aaa85c9f3's docstring) -- coalesced to '' so two
    # anonymous-client rows for the same bucket/IP still collide correctly.
    op.execute(
        f'CREATE UNIQUE INDEX {_UNIQUE_INDEX} ON client_hourly_aggregates '
        '(bucket_ts, client_ip, COALESCE("user", \'\'))'
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX {_UNIQUE_INDEX}')
    op.drop_table('client_hourly_aggregates')
