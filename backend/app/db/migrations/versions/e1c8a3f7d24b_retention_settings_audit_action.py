"""retention settings updated audit action

Revision ID: e1c8a3f7d24b
Revises: d9f4b2e7a1c6
Create Date: 2026-09-08 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c8a3f7d24b"
down_revision: str | None = "d9f4b2e7a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUE = "RETENTION_SETTINGS_UPDATED"
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
)
_ALL = _OLD + (_NEW_VALUE,)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{_NEW_VALUE}'")
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
