"""client_category_minute_aggregates

Revision ID: 2e7c4a1f803d
Revises: 8a1d3f6c9b02
Create Date: 2026-07-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2e7c4a1f803d'
down_revision: str | None = '8a1d3f6c9b02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_VALUES = (
    'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'MUSIC_STREAMING', 'GAMING', 'WORK_TOOLS',
    'SHOPPING', 'NEWS', 'GAMBLING', 'OTHER',
)


def upgrade() -> None:
    op.create_table(
        'client_category_minute_aggregates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('client_ip', sa.String(length=45), nullable=False),
        # create_type=False: domaincategorylabel already exists (created by
        # the domain_categories migration) -- this column reuses that same
        # Postgres enum type rather than trying to create it again.
        sa.Column(
            'category',
            sa.Enum(*_CATEGORY_VALUES, name='domaincategorylabel', create_type=False),
            nullable=False,
        ),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_client_category_minute_aggregates_bucket_ts',
        'client_category_minute_aggregates',
        ['bucket_ts'],
    )
    op.create_index(
        'ix_client_category_minute_aggregates_client_ip',
        'client_category_minute_aggregates',
        ['client_ip'],
    )
    op.create_index(
        'ix_client_category_bucket_ip_category',
        'client_category_minute_aggregates',
        ['bucket_ts', 'client_ip', 'category'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table('client_category_minute_aggregates')
