"""user branch changed audit action

Revision ID: a228da90977c
Revises: 60dde4013f46
Create Date: 2026-08-03 16:25:03.563670

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a228da90977c'
down_revision: str | None = '60dde4013f46'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED', 'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET',
    'EXPORT_SETTINGS_UPDATED', 'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED', 'REPORT_SENT_NOW',
)
_NEW_VALUES = (*_OLD_VALUES, 'USER_BRANCH_CHANGED')


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 3d8f5a2c9e14_add_adult_content_category.py for why this is one
        # ALTER TYPE ADD VALUE statement rather than a plain column change.
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'USER_BRANCH_CHANGED'")
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
        raise NotImplementedError(
            "Cannot downgrade: Postgres doesn't support removing enum values. "
            "Recreate the auditaction type manually if this is truly needed."
        )
    with op.batch_alter_table('audit_log_entries') as batch_op:
        batch_op.alter_column(
            'action',
            type_=sa.Enum(*_OLD_VALUES, name='auditaction'),
            existing_type=sa.Enum(*_NEW_VALUES, name='auditaction'),
            existing_nullable=False,
        )
