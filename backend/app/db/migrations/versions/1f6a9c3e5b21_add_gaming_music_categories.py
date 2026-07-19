"""add gaming and music_streaming domain categories

Revision ID: 1f6a9c3e5b21
Revises: 9ad7b1d281bd
Create Date: 2026-07-19 14:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1f6a9c3e5b21'
down_revision: str | None = '9ad7b1d281bd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'WORK_TOOLS', 'SHOPPING', 'NEWS', 'GAMBLING', 'OTHER',
)
_NEW_VALUES = (
    'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'MUSIC_STREAMING', 'GAMING', 'WORK_TOOLS', 'SHOPPING',
    'NEWS', 'GAMBLING', 'OTHER',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Postgres enums are a real type: existing values can't be added via
        # a plain ALTER COLUMN, and ADD VALUE can't run grouped with other
        # statements in the same DDL transaction on older servers -- one
        # statement per new value, each committed as it runs.
        op.execute("ALTER TYPE domaincategorylabel ADD VALUE IF NOT EXISTS 'MUSIC_STREAMING'")
        op.execute("ALTER TYPE domaincategorylabel ADD VALUE IF NOT EXISTS 'GAMING'")
    else:
        # SQLite has no native enum type -- SQLAlchemy emulates one with a
        # CHECK constraint, which can only be changed by recreating the
        # table (what batch mode does under the hood).
        with op.batch_alter_table('domain_categories') as batch_op:
            batch_op.alter_column(
                'category',
                type_=sa.Enum(*_NEW_VALUES, name='domaincategorylabel'),
                existing_type=sa.Enum(*_OLD_VALUES, name='domaincategorylabel'),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Postgres can't drop enum values at all without recreating the
        # type; downgrading here would require rewriting every row that
        # uses one of the removed values first, which is out of scope for
        # a reversible-in-the-common-case migration.
        raise NotImplementedError(
            "Cannot downgrade: Postgres doesn't support removing enum values. "
            "Recreate the domaincategorylabel type manually if this is truly needed."
        )
    with op.batch_alter_table('domain_categories') as batch_op:
        batch_op.alter_column(
            'category',
            type_=sa.Enum(*_OLD_VALUES, name='domaincategorylabel'),
            existing_type=sa.Enum(*_NEW_VALUES, name='domaincategorylabel'),
            existing_nullable=False,
        )
