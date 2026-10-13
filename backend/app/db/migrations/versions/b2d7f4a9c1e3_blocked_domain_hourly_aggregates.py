"""Hourly blocked-domain aggregates (denied vs 407, per proxy, per client)

Revision ID: b2d7f4a9c1e3
Revises: d1e5a9c3f7b0
Create Date: 2026-10-13 12:00:00.000000

Backs the Blocked page's "Domains" view. See
app/models/blocked_domain_aggregate.py. Empty on creation -- history before
the deploy is filled by scripts/backfill_blocked_domains.py, never here (it
scans raw_events, far too long for a migration).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d7f4a9c1e3"
down_revision: str | None = "d1e5a9c3f7b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blocked_domain_hourly_aggregates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bucket_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch", sa.String(length=64), nullable=False),
        sa.Column("proxy", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("denied_count", sa.Integer(), nullable=False),
        sa.Column("auth_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_blocked_domain_hourly_aggregates_bucket_ts"),
        "blocked_domain_hourly_aggregates",
        ["bucket_ts"],
        unique=False,
    )
    op.create_index(
        op.f("ix_blocked_domain_hourly_aggregates_domain"),
        "blocked_domain_hourly_aggregates",
        ["domain"],
        unique=False,
    )
    op.create_index(
        "ix_blocked_domain_hourly_key",
        "blocked_domain_hourly_aggregates",
        ["bucket_ts", "branch", "proxy", "domain"],
        unique=True,
    )

    op.create_table(
        "blocked_domain_client_hourly_aggregates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bucket_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch", sa.String(length=64), nullable=False),
        sa.Column("proxy", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=False),
        sa.Column("denied_count", sa.Integer(), nullable=False),
        sa.Column("auth_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_blocked_domain_client_hourly_aggregates_bucket_ts"),
        "blocked_domain_client_hourly_aggregates",
        ["bucket_ts"],
        unique=False,
    )
    op.create_index(
        "ix_blocked_domain_client_hourly_key",
        "blocked_domain_client_hourly_aggregates",
        ["bucket_ts", "branch", "proxy", "domain", "client_ip"],
        unique=True,
    )
    op.create_index(
        "ix_blocked_domain_client_hourly_domain_ts",
        "blocked_domain_client_hourly_aggregates",
        ["domain", "bucket_ts"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("blocked_domain_client_hourly_aggregates")
    op.drop_table("blocked_domain_hourly_aggregates")
