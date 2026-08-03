"""expanded audit actions

Revision ID: 21794ca3a016
Revises: 7b3f0d9a4c81
Create Date: 2026-08-03 15:47:54.206816

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '21794ca3a016'
down_revision: str | None = '7b3f0d9a4c81'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED',
)
_NEW_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED', 'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET',
    'EXPORT_SETTINGS_UPDATED', 'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED', 'REPORT_SENT_NOW',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 3d8f5a2c9e14_add_adult_content_category.py for why this is one
        # ALTER TYPE ADD VALUE statement per value rather than a plain
        # column change -- six values added together here since they're one
        # logical change (Phase 3 audit-trail expansion), not six unrelated
        # additions over time like the earlier per-value migrations.
        for value in (
            'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET', 'EXPORT_SETTINGS_UPDATED',
            'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED', 'REPORT_SENT_NOW',
        ):
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
        # Postgres can't drop enum values at all without recreating the
        # type; downgrading here would require rewriting every row that
        # uses any removed value first, which is out of scope for a
        # reversible-in-the-common-case migration.
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
