"""Squid operational per-minute aggregates + minute_aggregate response-time histogram

Revision ID: f3b8d1c6a274
Revises: c1e7a4b9d2f6
Create Date: 2026-09-04 12:00:00.000000

Backs the Analytics section's "Traffic & cache", "Blocks" and "Who" views:
four new per-minute aggregate tables (result code, HTTP method/status,
hierarchy code, per-user category) plus a six-band response-time histogram
folded into minute_aggregates. All populated in the same Aggregator.flush()
pass as the existing buckets. See app/models/ops_aggregate.py.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3b8d1c6a274'
down_revision: str | None = 'c1e7a4b9d2f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERF_COLUMNS = (
    'duration_sum_ms',
    'dur_lt_100',
    'dur_lt_300',
    'dur_lt_1000',
    'dur_lt_3000',
    'dur_lt_10000',
    'dur_gte_10000',
)

_CATEGORY_VALUES = (
    'UNCATEGORIZED',
    'SOCIAL_MEDIA',
    'VIDEO_STREAMING',
    'MUSIC_STREAMING',
    'GAMING',
    'WORK_TOOLS',
    'SHOPPING',
    'NEWS',
    'GAMBLING',
    'ADULT_CONTENT',
    'OTHER',
)


def upgrade() -> None:
    # Backfilled to 0, not NULL -- existing minute rows predate response-time
    # tracking; analytics_service.get_response_time treats a zero total
    # count as "no data for this window" rather than dividing by zero.
    op.add_column(
        'minute_aggregates',
        sa.Column('duration_sum_ms', sa.BigInteger(), nullable=False, server_default='0'),
    )
    for name in _PERF_COLUMNS[1:]:
        op.add_column(
            'minute_aggregates', sa.Column(name, sa.Integer(), nullable=False, server_default='0')
        )

    op.create_table(
        'result_code_minute_aggregates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_result_code_minute_aggregates_bucket_ts'),
        'result_code_minute_aggregates',
        ['bucket_ts'],
        unique=False,
    )
    op.create_index(
        op.f('ix_result_code_minute_aggregates_branch'),
        'result_code_minute_aggregates',
        ['branch'],
        unique=False,
    )
    op.create_index(
        'ix_result_code_bucket_branch_action',
        'result_code_minute_aggregates',
        ['bucket_ts', 'branch', 'action'],
        unique=True,
    )

    op.create_table(
        'http_minute_aggregates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('method', sa.String(length=16), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_http_minute_aggregates_bucket_ts'), 'http_minute_aggregates', ['bucket_ts'], unique=False
    )
    op.create_index(
        op.f('ix_http_minute_aggregates_branch'), 'http_minute_aggregates', ['branch'], unique=False
    )
    op.create_index(
        'ix_http_bucket_branch_method_status',
        'http_minute_aggregates',
        ['bucket_ts', 'branch', 'method', 'status_code'],
        unique=True,
    )

    op.create_table(
        'hierarchy_minute_aggregates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('hierarchy_code', sa.String(length=64), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_hierarchy_minute_aggregates_bucket_ts'),
        'hierarchy_minute_aggregates',
        ['bucket_ts'],
        unique=False,
    )
    op.create_index(
        op.f('ix_hierarchy_minute_aggregates_branch'),
        'hierarchy_minute_aggregates',
        ['branch'],
        unique=False,
    )
    op.create_index(
        'ix_hierarchy_bucket_branch_code',
        'hierarchy_minute_aggregates',
        ['bucket_ts', 'branch', 'hierarchy_code'],
        unique=True,
    )

    op.create_table(
        'user_category_minute_aggregates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('user', sa.String(length=255), nullable=False),
        # create_type=False: domaincategorylabel already exists (see the
        # client_category_minute_aggregates migration) -- reuse it.
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
        op.f('ix_user_category_minute_aggregates_bucket_ts'),
        'user_category_minute_aggregates',
        ['bucket_ts'],
        unique=False,
    )
    op.create_index(
        op.f('ix_user_category_minute_aggregates_branch'),
        'user_category_minute_aggregates',
        ['branch'],
        unique=False,
    )
    op.create_index(
        op.f('ix_user_category_minute_aggregates_user'),
        'user_category_minute_aggregates',
        ['user'],
        unique=False,
    )
    op.create_index(
        'ix_user_category_bucket_branch_user_category',
        'user_category_minute_aggregates',
        ['bucket_ts', 'branch', 'user', 'category'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table('user_category_minute_aggregates')
    op.drop_table('hierarchy_minute_aggregates')
    op.drop_table('http_minute_aggregates')
    op.drop_table('result_code_minute_aggregates')
    for name in reversed(_PERF_COLUMNS):
        op.drop_column('minute_aggregates', name)
