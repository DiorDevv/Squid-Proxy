"""domain categories

Revision ID: 9ad7b1d281bd
Revises: c78d2ae9a0b3
Create Date: 2026-07-18 22:46:24.542815

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9ad7b1d281bd'
down_revision: str | None = 'c78d2ae9a0b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'domain_categories',
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column(
            'category',
            sa.Enum(
                'UNCATEGORIZED', 'SOCIAL_MEDIA', 'VIDEO_STREAMING', 'WORK_TOOLS', 'SHOPPING', 'NEWS',
                'GAMBLING', 'OTHER', name='domaincategorylabel',
            ),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('domain'),
    )


def downgrade() -> None:
    op.drop_table('domain_categories')
