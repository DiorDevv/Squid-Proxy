"""add adult_content domain category

Revision ID: 3d8f5a2c9e14
Revises: b7e3d1a4c8f2
Create Date: 2026-07-21 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3d8f5a2c9e14'
down_revision: str | None = 'b7e3d1a4c8f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = (
    'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'MUSIC_STREAMING', 'GAMING', 'WORK_TOOLS', 'SHOPPING',
    'NEWS', 'GAMBLING', 'OTHER',
)
_NEW_VALUES = (
    'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'MUSIC_STREAMING', 'GAMING', 'WORK_TOOLS', 'SHOPPING',
    'NEWS', 'GAMBLING', 'ADULT_CONTENT', 'OTHER',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 1f6a9c3e5b21_add_gaming_music_categories.py for why this is one
        # ALTER TYPE ADD VALUE statement rather than a plain column change.
        op.execute("ALTER TYPE domaincategorylabel ADD VALUE IF NOT EXISTS 'ADULT_CONTENT'")
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
        # uses the removed value first, which is out of scope for a
        # reversible-in-the-common-case migration.
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
