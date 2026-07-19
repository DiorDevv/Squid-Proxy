"""aggregate table unique constraints (prevent duplicate-flush corruption)

Revision ID: 466aaa85c9f3
Revises: 6024333e2772
Create Date: 2026-07-18 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '466aaa85c9f3'
down_revision: str | None = '6024333e2772'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The aggregator upserts by selecting-then-incrementing a row keyed on these
# columns (see app/services/aggregator.py). That's only safe as long as at
# most one row can ever exist per key; today a single sequential aggregator
# task guarantees that, but nothing in the schema enforced it. These indexes
# make a future duplicate-flush or multi-instance-aggregator bug fail loudly
# (IntegrityError) instead of silently splitting/undercounting stats.
#
# `client_minute_aggregates.user` is nullable (unauthenticated Squid
# traffic), and plain SQL unique constraints treat NULL as distinct from
# itself -- so that index is built over coalesce(user, '') to also catch
# duplicates for anonymous (no-user) clients, not just authenticated ones.

_DOMAIN_INDEX_OLD = "ix_domain_bucket_domain"
_CLIENT_INDEX_NEW = "ix_client_bucket_ip_user_unique"


def upgrade() -> None:
    op.drop_index(_DOMAIN_INDEX_OLD, table_name="domain_minute_aggregates")
    op.create_index(
        _DOMAIN_INDEX_OLD, "domain_minute_aggregates", ["bucket_ts", "domain"], unique=True
    )
    op.execute(
        f'CREATE UNIQUE INDEX {_CLIENT_INDEX_NEW} ON client_minute_aggregates '
        f'(bucket_ts, client_ip, COALESCE("user", \'\'))'
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX {_CLIENT_INDEX_NEW}")
    op.drop_index(_DOMAIN_INDEX_OLD, table_name="domain_minute_aggregates")
    op.create_index(
        _DOMAIN_INDEX_OLD, "domain_minute_aggregates", ["bucket_ts", "domain"], unique=False
    )
