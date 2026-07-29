"""export shared audit action

Revision ID: 7b3f0d9a4c81
Revises: 1a9e4f7c2d63
Create Date: 2026-07-29 07:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b3f0d9a4c81'
down_revision: str | None = '1a9e4f7c2d63'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED',
)
_NEW_VALUES = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 3d8f5a2c9e14_add_adult_content_category.py for why this is one
        # ALTER TYPE ADD VALUE statement rather than a plain column change.
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'EXPORT_SHARED'")
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
        # uses the removed value first, which is out of scope for a
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
