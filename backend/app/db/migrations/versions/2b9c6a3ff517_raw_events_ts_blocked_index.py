"""raw_events: add (timestamp, blocked) index for the Blocked-page query pattern

Revision ID: 2b9c6a3ff517
Revises: 5f9b2d4e7a13
Create Date: 2026-07-20 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2b9c6a3ff517'
down_revision: str | None = '5f9b2d4e7a13'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# event_query_service.get_events (which backs the Blocked page and
# export_service's CSV/JSON export) filters WHERE blocked = true AND
# timestamp BETWEEN ? AND ? ORDER BY timestamp DESC. The existing standalone
# `blocked` index only helps a bare equality lookup; it can't also serve the
# timestamp range/order. Leading with `timestamp` lets the range scan and
# the blocked filter both use the same index, and keeps ORDER BY timestamp
# DESC index-ordered instead of requiring a separate sort.
_INDEX = "ix_raw_events_ts_blocked"


def upgrade() -> None:
    op.create_index(_INDEX, "raw_events", ["timestamp", "blocked"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="raw_events")
