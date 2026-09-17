"""watchlist entries

Revision ID: a7d4e9f21b60
Revises: f3b8d1c6a274
Create Date: 2026-09-04 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d4e9f21b60'
down_revision: str | None = 'f3b8d1c6a274'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'watchlist_entries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column(
            'target_type',
            sa.Enum('CLIENT_IP', 'DOMAIN', 'USER', name='watchlisttargettype'),
            nullable=False,
        ),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_alerted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_watchlist_entries_value'), 'watchlist_entries', ['value'], unique=False
    )
    op.create_index(
        'ix_watchlist_type_value_branch',
        'watchlist_entries',
        ['target_type', 'value', 'branch'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_watchlist_type_value_branch', table_name='watchlist_entries')
    op.drop_index(op.f('ix_watchlist_entries_value'), table_name='watchlist_entries')
    op.drop_table('watchlist_entries')
    sa.Enum(name='watchlisttargettype').drop(op.get_bind(), checkfirst=True)
