"""user branch scoping

Revision ID: 60dde4013f46
Revises: 21794ca3a016
Create Date: 2026-08-03 16:18:22.776636

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '60dde4013f46'
down_revision: str | None = '21794ca3a016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default -- every existing row gets NULL (unrestricted,
    # identical to today's behavior for every current user). Ordinary
    # column add, not an enum type, so unlike the audit-action migrations
    # this needs no Postgres/SQLite branching.
    op.add_column('users', sa.Column('branch', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'branch')
