"""export job file size

Revision ID: 9a3d7c1e5f28
Revises: 2f6b8e4d1a97
Create Date: 2026-07-22 13:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9a3d7c1e5f28'
down_revision: str | None = '2f6b8e4d1a97'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('export_jobs', sa.Column('file_size_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('export_jobs', 'file_size_bytes')
