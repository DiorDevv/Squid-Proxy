"""anomaly event kind and params for localized insights

Revision ID: b3e9c7a2f1d4
Revises: d5f8a3c1e947
Create Date: 2026-08-20 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3e9c7a2f1d4'
down_revision: str | None = 'd5f8a3c1e947'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default/backfill: existing rows keep their English-only
    # title/description (app.insights.base.Anomaly.kind/params didn't exist
    # yet when they were written) and the frontend falls back to those
    # verbatim when kind is NULL -- see frontend/src/lib/insights.ts.
    op.add_column('anomaly_events', sa.Column('kind', sa.String(length=32), nullable=True))
    op.add_column('anomaly_events', sa.Column('params', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('anomaly_events', 'params')
    op.drop_column('anomaly_events', 'kind')
