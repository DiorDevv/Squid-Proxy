"""GIN trigram indexes so free-text search (ILIKE '%x%') stops seq-scanning

Revision ID: c9e4b7a15d02
Revises: f2a7c4e9b183
Create Date: 2026-09-10 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e4b7a15d02"
down_revision: str | None = "f2a7c4e9b183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# /api/events, /api/clients and /api/domains/search all filter with
# `col ILIKE '%term%'`, which no btree index can serve -- at ~60M raw_events
# rows on the production VM a single search seq-scans for tens of seconds.
# pg_trgm + a GIN index per searched column makes those ILIKEs
# index-assisted. Postgres only; on SQLite (tests/CI) this is a no-op.
#
# `raw_events.url` is intentionally absent: it's the full-URL Text column,
# far the most expensive to trigram, and neither the events nor the blocked
# search advertises URL matching (see event_query_service.build_event_conditions).
_TRGM_INDEXES: list[tuple[str, str, str]] = [
    ("ix_raw_events_client_ip_trgm", "raw_events", "client_ip"),
    ("ix_raw_events_domain_trgm", "raw_events", "domain"),
    ("ix_raw_events_user_trgm", "raw_events", '"user"'),
    ("ix_raw_events_peer_trgm", "raw_events", "peer"),
    ("ix_dma_domain_trgm", "domain_minute_aggregates", "domain"),
    ("ix_cma_client_ip_trgm", "client_minute_aggregates", "client_ip"),
    ("ix_cma_user_trgm", "client_minute_aggregates", '"user"'),
    ("ix_cha_client_ip_trgm", "client_hourly_aggregates", "client_ip"),
    ("ix_cha_user_trgm", "client_hourly_aggregates", '"user"'),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # CONCURRENTLY, in its own autocommit block (same reason as
    # 8a1d3f6c9b02): a plain CREATE INDEX locks each table against writes
    # for the whole build and this migration runs automatically on every
    # app start. `alembic upgrade head` therefore returns quickly while the
    # indexes finish building in the background -- search stays slow for
    # those few minutes, then flips to fast. IF NOT EXISTS so an
    # interrupted concurrent build can be retried by re-running.
    with op.get_context().autocommit_block():
        for name, table, column in _TRGM_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {table} USING gin ({column} gin_trgm_ops)"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name, _table, _column in _TRGM_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
