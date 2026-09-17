"""system_events table for durable operational-failure history

Revision ID: c5d8e1f3a92b
Revises: a2f9c7e4b1d8
Create Date: 2026-09-08 12:00:00.000000

Every notify_operator_failure() call (log tailer down, a background job
erroring, a backup/retention/archiving run failing) now also writes a row
here, so Settings -> System health can show what has broken lately even
when no OPS_ALERT_WEBHOOK_URL is configured. Pruned by RetentionJob.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d8e1f3a92b"
down_revision: str | None = "a2f9c7e4b1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # A partially-applied earlier attempt of this migration could leave the
    # enum type behind without the table (Postgres); drop it so create_table
    # below can (re)create it cleanly. Nothing references it yet.
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS systemeventseverity")

    # sa.Enum inline in the column -- create_table emits CREATE TYPE for it
    # on Postgres, matching how anomaly_events / audit_log were created. No
    # explicit .create()/.drop() (doing both double-creates the type).
    op.create_table(
        "system_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("WARNING", "ERROR", name="systemeventseverity"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_events_created_at", "system_events", ["created_at"])
    op.create_index("ix_system_events_source", "system_events", ["source"])
    op.create_index("ix_system_events_severity", "system_events", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_system_events_severity", table_name="system_events")
    op.drop_index("ix_system_events_source", table_name="system_events")
    op.drop_index("ix_system_events_created_at", table_name="system_events")
    op.drop_table("system_events")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS systemeventseverity")
