"""totp audit actions

Revision ID: a9d3f6c2e871
Revises: f7a4c8e2b615
Create Date: 2026-08-21 12:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9d3f6c2e871'
down_revision: str | None = 'f7a4c8e2b615'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED', 'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET',
    'EXPORT_SETTINGS_UPDATED', 'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED', 'REPORT_SENT_NOW',
    'USER_BRANCH_CHANGED',
)
_NEW_VALUES = (
    *_OLD_VALUES, 'TOTP_ENABLED', 'TOTP_DISABLED', 'TOTP_RECOVERY_CODE_USED',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 21794ca3a016_expanded_audit_actions.py for why this is one
        # ALTER TYPE ADD VALUE statement per value.
        for value in ('TOTP_ENABLED', 'TOTP_DISABLED', 'TOTP_RECOVERY_CODE_USED'):
            op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")
    else:
        # SQLite has no native enum type -- SQLAlchemy emulates one with a
        # CHECK constraint, which can only be changed by recreating the
        # table (what batch mode does under the hood).
        with op.batch_alter_table('audit_log_entries') as batch_op:
            batch_op.alter_column(
                'action',
                type_=sa.Enum(*_NEW_VALUES, name='auditaction'),
                existing_type=sa.Enum(*_OLD_VALUES, name='auditaction'),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Postgres can't drop enum values without recreating the type;
        # downgrading here would require rewriting every row that used one
        # of the new values first. No known caller needs this downgrade
        # path, so it's left unsupported (matches
        # 21794ca3a016_expanded_audit_actions.py's own precedent).
        raise NotImplementedError(
            "Cannot remove enum values from a Postgres type without rewriting affected rows first."
        )
    with op.batch_alter_table('audit_log_entries') as batch_op:
        batch_op.alter_column(
            'action',
            type_=sa.Enum(*_OLD_VALUES, name='auditaction'),
            existing_type=sa.Enum(*_NEW_VALUES, name='auditaction'),
            existing_nullable=False,
        )
