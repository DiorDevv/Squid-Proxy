"""retention_settings table (admin-tunable raw_events window + archive-lag guard)

Revision ID: d9f4b2e7a1c6
Revises: c5d8e1f3a92b
Create Date: 2026-09-08 14:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f4b2e7a1c6"
down_revision: str | None = "c5d8e1f3a92b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_events_days", sa.Integer(), nullable=False),
        sa.Column("halt_purge_if_archive_lag_days", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("retention_settings")
