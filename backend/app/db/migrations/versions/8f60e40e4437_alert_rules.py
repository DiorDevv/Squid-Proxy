"""alert_rules table (admin-defined custom threshold rules)

Revision ID: 8f60e40e4437
Revises: c9e4b7a15d02
Create Date: 2026-09-11 08:04:47.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f60e40e4437"
down_revision: str | None = "c9e4b7a15d02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEVERITY_VALUES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _severity_column_type() -> sa.types.TypeEngine:
    """A `severity` column that references the *existing* `anomalyseverity`
    enum (created by migration c3dd467754e8 for anomaly_events) without
    trying to CREATE it again -- same reasoning/workaround as
    f3b8d1c6a274's `_category_column_type` for `domaincategorylabel`:
    plain `sa.Enum(..., create_type=False)` alone doesn't reliably suppress
    the CREATE on newer SQLAlchemy; the dialect-specific postgresql.ENUM
    does. SQLite has no enum types so plain sa.Enum (VARCHAR + CHECK) is
    fine there.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.ENUM(*_SEVERITY_VALUES, name="anomalyseverity", create_type=False)
    return sa.Enum(*_SEVERITY_VALUES, name="anomalyseverity", create_type=False)


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("branch", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("CLIENT_IP", "DOMAIN", "BRANCH", name="alertrulescope"),
            nullable=False,
        ),
        sa.Column(
            "metric",
            sa.Enum(
                "REQUEST_COUNT", "BLOCKED_COUNT", "TOTAL_BYTES", "BYTES_RECEIVED", name="alertrulemetric"
            ),
            nullable=False,
        ),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.BigInteger(), nullable=False),
        sa.Column("severity", _severity_column_type(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_rules_branch"), "alert_rules", ["branch"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_rules_branch"), table_name="alert_rules")
    op.drop_table("alert_rules")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="alertrulescope").drop(bind, checkfirst=True)
        sa.Enum(name="alertrulemetric").drop(bind, checkfirst=True)
        # anomalyseverity is NOT dropped -- it's still owned/used by
        # anomaly_events (created before this migration, outlives it).
