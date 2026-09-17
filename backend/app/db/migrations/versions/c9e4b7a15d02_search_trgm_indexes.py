"""pg_trgm extension for index-backed free-text search

Revision ID: c9e4b7a15d02
Revises: f2a7c4e9b183
Create Date: 2026-09-10 12:00:00.000000

This migration only enables the extension -- fast, safe to run on startup.
The GIN trigram indexes themselves are NOT built here: on a populated
raw_events table (~60M rows on the production VM) a `CREATE INDEX` would
either lock the table against writes for the whole build or, with
CONCURRENTLY, block this migration -- and `alembic upgrade head` runs
before the backend serves traffic, so either way the app can't come up
until the build finishes. Build them out-of-band instead, while the app
runs, with:

    backend/scripts/build_search_indexes.sh        (Docker)
    docker compose exec -T postgres psql ... -f scripts/build_search_indexes.sql

Search still works without them -- just slower -- so this is a
run-it-when-convenient step, not a deploy blocker. A fresh install has ~0
rows, so running the script there is instant.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e4b7a15d02"
down_revision: str | None = "f2a7c4e9b183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Left in place -- an extension other objects may depend on is not worth
    # dropping on a rollback, and DROP EXTENSION would fail anyway while any
    # trigram index still exists.
    pass
