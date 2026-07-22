"""export job cancelled status

Revision ID: 8c4e2a71f9d3
Revises: 5f19c6b8d4a7
Create Date: 2026-07-22 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8c4e2a71f9d3'
down_revision: str | None = '5f19c6b8d4a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = ('PENDING', 'RUNNING', 'DONE', 'FAILED')
_NEW_VALUES = ('PENDING', 'RUNNING', 'DONE', 'FAILED', 'CANCELLED')


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 3d8f5a2c9e14_add_adult_content_category.py for why this is one
        # ALTER TYPE ADD VALUE statement rather than a plain column change.
        op.execute("ALTER TYPE exportjobstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
    else:
        # SQLite has no native enum type -- SQLAlchemy emulates one with a
        # CHECK constraint, which can only be changed by recreating the
        # table (what batch mode does under the hood).
        with op.batch_alter_table('export_jobs') as batch_op:
            batch_op.alter_column(
                'status',
                type_=sa.Enum(*_NEW_VALUES, name='exportjobstatus'),
                existing_type=sa.Enum(*_OLD_VALUES, name='exportjobstatus'),
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
            "Recreate the exportjobstatus type manually if this is truly needed."
        )
    with op.batch_alter_table('export_jobs') as batch_op:
        batch_op.alter_column(
            'status',
            type_=sa.Enum(*_OLD_VALUES, name='exportjobstatus'),
            existing_type=sa.Enum(*_NEW_VALUES, name='exportjobstatus'),
            existing_nullable=False,
        )
