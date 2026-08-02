"""branch dimension (multi-source ingestion)

Revision ID: a4f7c2e9b1d6
Revises: 2b9c6a3ff517
Create Date: 2026-07-20 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4f7c2e9b1d6'
down_revision: str | None = '2b9c6a3ff517'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches app.core.config.DEFAULT_BRANCH -- every existing row (all
# ingested before multi-branch support existed) is backfilled under this
# name, keeping single-branch deployments working with no config change.
_DEFAULT_BRANCH = 'default'

_CLIENT_MINUTE_UNIQUE = 'ix_client_bucket_ip_user_unique'
_CLIENT_HOURLY_UNIQUE = 'ix_client_hourly_bucket_ip_user_unique'


def _branch_column() -> sa.Column:
    return sa.Column(
        'branch', sa.String(length=64), nullable=False, server_default=_DEFAULT_BRANCH
    )


def upgrade() -> None:
    # raw_events: plain column + a (branch, timestamp) index for per-branch
    # event/export queries; no uniqueness concern here (raw_events is a
    # plain append, never upserted). Built CONCURRENTLY, in its own
    # autocommit block: raw_events is the one table here that can be in the
    # millions of rows (see the 8a1d3f6c9b02/2b9c6a3ff517 migrations' own
    # docstrings for the measured scale), so a plain CREATE INDEX would hold
    # an exclusive lock against the aggregator's writes for the whole build.
    # The other tables touched below are the much smaller per-minute/hourly
    # aggregates, where that risk doesn't apply.
    op.add_column('raw_events', _branch_column())
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_raw_events_branch_ts',
            'raw_events',
            ['branch', 'timestamp'],
            postgresql_concurrently=True,
        )

    # minute_aggregates: bucket_ts alone used to be the whole unique key (one
    # global total per minute); now (bucket_ts, branch), since each branch
    # gets its own per-minute total.
    op.add_column('minute_aggregates', _branch_column())
    op.drop_index('ix_minute_aggregates_bucket_ts', table_name='minute_aggregates')
    op.create_index('ix_minute_aggregates_bucket_ts', 'minute_aggregates', ['bucket_ts'])
    op.create_index(
        'ix_minute_bucket_branch', 'minute_aggregates', ['bucket_ts', 'branch'], unique=True
    )

    # domain_minute_aggregates: (bucket_ts, domain) unique -> (bucket_ts,
    # domain, branch), so the same domain in two branches' logs in the same
    # minute gets two rows instead of one merged (and wrong) one.
    op.add_column('domain_minute_aggregates', _branch_column())
    op.drop_index('ix_domain_bucket_domain', table_name='domain_minute_aggregates')
    op.create_index(
        'ix_domain_bucket_domain',
        'domain_minute_aggregates',
        ['bucket_ts', 'domain', 'branch'],
        unique=True,
    )

    # client_minute_aggregates: same nullable-`user` expression-index
    # treatment as migration 466aaa85c9f3 (coalesce to '' so NULL-vs-NULL
    # doesn't defeat uniqueness), branch added to both the plain lookup
    # index and the real unique constraint.
    op.add_column('client_minute_aggregates', _branch_column())
    op.create_index(
        'ix_client_minute_aggregates_branch', 'client_minute_aggregates', ['branch']
    )
    op.execute(f'DROP INDEX {_CLIENT_MINUTE_UNIQUE}')
    op.execute(
        f'CREATE UNIQUE INDEX {_CLIENT_MINUTE_UNIQUE} ON client_minute_aggregates '
        '(bucket_ts, client_ip, branch, COALESCE("user", \'\'))'
    )

    # client_category_minute_aggregates: (bucket_ts, client_ip, category)
    # unique -> add branch.
    op.add_column('client_category_minute_aggregates', _branch_column())
    op.create_index(
        'ix_client_category_minute_aggregates_branch',
        'client_category_minute_aggregates',
        ['branch'],
    )
    op.drop_index(
        'ix_client_category_bucket_ip_category', table_name='client_category_minute_aggregates'
    )
    op.create_index(
        'ix_client_category_bucket_ip_category',
        'client_category_minute_aggregates',
        ['bucket_ts', 'client_ip', 'category', 'branch'],
        unique=True,
    )

    # client_hourly_aggregates: same expression-index treatment as
    # client_minute_aggregates above.
    op.add_column('client_hourly_aggregates', _branch_column())
    op.create_index(
        'ix_client_hourly_aggregates_branch', 'client_hourly_aggregates', ['branch']
    )
    op.execute(f'DROP INDEX {_CLIENT_HOURLY_UNIQUE}')
    op.execute(
        f'CREATE UNIQUE INDEX {_CLIENT_HOURLY_UNIQUE} ON client_hourly_aggregates '
        '(bucket_ts, client_ip, branch, COALESCE("user", \'\'))'
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX {_CLIENT_HOURLY_UNIQUE}')
    op.execute(
        f'CREATE UNIQUE INDEX {_CLIENT_HOURLY_UNIQUE} ON client_hourly_aggregates '
        '(bucket_ts, client_ip, COALESCE("user", \'\'))'
    )
    op.drop_index('ix_client_hourly_aggregates_branch', table_name='client_hourly_aggregates')
    op.drop_column('client_hourly_aggregates', 'branch')

    op.drop_index(
        'ix_client_category_bucket_ip_category', table_name='client_category_minute_aggregates'
    )
    op.create_index(
        'ix_client_category_bucket_ip_category',
        'client_category_minute_aggregates',
        ['bucket_ts', 'client_ip', 'category'],
        unique=True,
    )
    op.drop_index(
        'ix_client_category_minute_aggregates_branch',
        table_name='client_category_minute_aggregates',
    )
    op.drop_column('client_category_minute_aggregates', 'branch')

    op.execute(f'DROP INDEX {_CLIENT_MINUTE_UNIQUE}')
    op.execute(
        f'CREATE UNIQUE INDEX {_CLIENT_MINUTE_UNIQUE} ON client_minute_aggregates '
        '(bucket_ts, client_ip, COALESCE("user", \'\'))'
    )
    op.drop_index('ix_client_minute_aggregates_branch', table_name='client_minute_aggregates')
    op.drop_column('client_minute_aggregates', 'branch')

    op.drop_index('ix_domain_bucket_domain', table_name='domain_minute_aggregates')
    op.create_index(
        'ix_domain_bucket_domain', 'domain_minute_aggregates', ['bucket_ts', 'domain'], unique=True
    )
    op.drop_column('domain_minute_aggregates', 'branch')

    op.drop_index('ix_minute_bucket_branch', table_name='minute_aggregates')
    op.drop_index('ix_minute_aggregates_bucket_ts', table_name='minute_aggregates')
    op.create_index(
        'ix_minute_aggregates_bucket_ts', 'minute_aggregates', ['bucket_ts'], unique=True
    )
    op.drop_column('minute_aggregates', 'branch')

    with op.get_context().autocommit_block():
        op.drop_index(
            'ix_raw_events_branch_ts', table_name='raw_events', postgresql_concurrently=True
        )
    op.drop_column('raw_events', 'branch')
