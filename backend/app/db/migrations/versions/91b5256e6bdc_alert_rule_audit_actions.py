"""alert rule created/updated/deleted audit actions

Revision ID: 91b5256e6bdc
Revises: 8f60e40e4437
Create Date: 2026-09-11 08:37:16.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91b5256e6bdc"
down_revision: str | None = "8f60e40e4437"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("ALERT_RULE_CREATED", "ALERT_RULE_UPDATED", "ALERT_RULE_DELETED")
_OLD = (
    "USER_CREATED",
    "USER_ROLE_CHANGED",
    "USER_PASSWORD_RESET",
    "USER_DELETED",
    "EXPORT_CREATED",
    "EXPORT_DOWNLOADED",
    "EXPORT_SHARED",
    "ALERT_SETTINGS_UPDATED",
    "DOMAIN_CATEGORY_SET",
    "DOMAIN_CATEGORY_IMPORTED",
    "EXPORT_SETTINGS_UPDATED",
    "EXPORT_CANCELLED",
    "EXPORT_SHARE_REVOKED",
    "REPORT_SENT_NOW",
    "USER_BRANCH_CHANGED",
    "TOTP_ENABLED",
    "TOTP_DISABLED",
    "TOTP_RECOVERY_CODE_USED",
    "TELEGRAM_LINKED",
    "CLIENT_ACTIVITY_VIEWED",
    "EVENT_SEARCH_RUN",
    "ANALYTICS_ACTOR_VIEWED",
    "SUBJECT_DOSSIER_EXPORTED",
    "RETENTION_SETTINGS_UPDATED",
)
_ALL = _OLD + _NEW_VALUES


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")
    else:
        with op.batch_alter_table("audit_log_entries") as batch_op:
            batch_op.alter_column(
                "action",
                type_=sa.Enum(*_ALL, name="auditaction"),
                existing_type=sa.Enum(*_OLD, name="auditaction"),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        raise NotImplementedError("Cannot downgrade: Postgres doesn't support removing enum values.")
    with op.batch_alter_table("audit_log_entries") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_OLD, name="auditaction"),
            existing_type=sa.Enum(*_ALL, name="auditaction"),
            existing_nullable=False,
        )
