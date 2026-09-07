"""auditor role + read-access audit actions

One logical change (docs/PRODUCT.md's compliance push): a read-only
oversight role, and audit-log actions for *who looked at whom* -- viewing a
subject's activity, running an event search, opening a per-actor analytics
drill-down.

Revision ID: d7e2a9c4f318
Revises: a7d4e9f21b60
Create Date: 2026-09-04 18:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e2a9c4f318"
down_revision: str | None = "a7d4e9f21b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_OLD = ("ADMIN", "VIEWER")
_ROLE_NEW = ("ADMIN", "VIEWER", "AUDITOR")

_ACTION_NEW_VALUES = ("CLIENT_ACTIVITY_VIEWED", "EVENT_SEARCH_RUN", "ANALYTICS_ACTOR_VIEWED")
_ACTION_OLD = (
    "USER_CREATED", "USER_ROLE_CHANGED", "USER_PASSWORD_RESET", "USER_DELETED", "EXPORT_CREATED",
    "EXPORT_DOWNLOADED", "EXPORT_SHARED", "ALERT_SETTINGS_UPDATED", "DOMAIN_CATEGORY_SET",
    "DOMAIN_CATEGORY_IMPORTED", "EXPORT_SETTINGS_UPDATED", "EXPORT_CANCELLED",
    "EXPORT_SHARE_REVOKED", "REPORT_SENT_NOW", "USER_BRANCH_CHANGED", "TOTP_ENABLED",
    "TOTP_DISABLED", "TOTP_RECOVERY_CODE_USED", "TELEGRAM_LINKED",
)
_ACTION_ALL = _ACTION_OLD + _ACTION_NEW_VALUES


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ALTER TYPE ADD VALUE per value -- see 21794ca3a016 for why.
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'AUDITOR'")
        for value in _ACTION_NEW_VALUES:
            op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")
    else:
        # SQLite emulates enums with a CHECK constraint; batch mode recreates
        # the table to change it.
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "role",
                type_=sa.Enum(*_ROLE_NEW, name="userrole"),
                existing_type=sa.Enum(*_ROLE_OLD, name="userrole"),
                existing_nullable=False,
            )
        with op.batch_alter_table("audit_log_entries") as batch_op:
            batch_op.alter_column(
                "action",
                type_=sa.Enum(*_ACTION_ALL, name="auditaction"),
                existing_type=sa.Enum(*_ACTION_OLD, name="auditaction"),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        raise NotImplementedError(
            "Cannot downgrade: Postgres doesn't support removing enum values."
        )
    with op.batch_alter_table("audit_log_entries") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_ACTION_OLD, name="auditaction"),
            existing_type=sa.Enum(*_ACTION_ALL, name="auditaction"),
            existing_nullable=False,
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "role",
            type_=sa.Enum(*_ROLE_OLD, name="userrole"),
            existing_type=sa.Enum(*_ROLE_NEW, name="userrole"),
            existing_nullable=False,
        )
