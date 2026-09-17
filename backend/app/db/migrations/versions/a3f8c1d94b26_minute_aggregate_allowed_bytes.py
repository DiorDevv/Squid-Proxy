"""minute_aggregates.allowed_bytes / allowed_bytes_received

Revision ID: a3f8c1d94b26
Revises: 91b5256e6bdc
Create Date: 2026-09-16 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f8c1d94b26"
down_revision: str | None = "91b5256e6bdc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # minute_aggregates.total_bytes/bytes_received deliberately keep including
    # blocked-request bytes -- that column backs the Overview-wide bandwidth
    # total, where "how much traffic touched this box" (including a denial
    # page's few bytes) is the right question. But per-branch attribution
    # reads (branch breakdown/trend -- "how much did branch X transfer") were
    # reading that same column and silently inheriting blocked bytes into a
    # number a reader would take as "what actually got through". These two
    # new columns give per-branch attribution its own correct source without
    # changing the Overview total's meaning.
    op.add_column(
        "minute_aggregates",
        sa.Column("allowed_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "minute_aggregates",
        sa.Column("allowed_bytes_received", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("minute_aggregates", "allowed_bytes_received")
    op.drop_column("minute_aggregates", "allowed_bytes")
