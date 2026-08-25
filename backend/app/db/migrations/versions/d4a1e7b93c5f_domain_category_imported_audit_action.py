"""domain category imported audit action

Revision ID: d4a1e7b93c5f
Revises: a9d3f6c2e871
Create Date: 2026-08-24 15:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a1e7b93c5f'
down_revision: str | None = 'a9d3f6c2e871'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED', 'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET',
    'EXPORT_SETTINGS_UPDATED', 'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED', 'REPORT_SENT_NOW',
    'USER_BRANCH_CHANGED', 'TOTP_ENABLED', 'TOTP_DISABLED', 'TOTP_RECOVERY_CODE_USED',
)
_NEW_VALUES = (
    *_OLD_VALUES, 'DOMAIN_CATEGORY_IMPORTED',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 21794ca3a016_expanded_audit_actions.py for why this is one
        # ALTER TYPE ADD VALUE statement per value.
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'DOMAIN_CATEGORY_IMPORTED'")
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
        # downgrading here would require rewriting every row that used the
        # new value first. No known caller needs this downgrade path,
        # matches a9d3f6c2e871_totp_audit_actions.py's own precedent.
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
