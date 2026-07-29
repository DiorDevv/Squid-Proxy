"""export job filters, column selection, checksum, share link

Revision ID: 1a9e4f7c2d63
Revises: f2a8c5d1e9b7
Create Date: 2026-07-29 07:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1a9e4f7c2d63'
down_revision: str | None = 'f2a8c5d1e9b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('export_jobs', sa.Column('domain', sa.String(length=255), nullable=True))
    op.add_column('export_jobs', sa.Column('category', sa.String(length=32), nullable=True))
    op.add_column('export_jobs', sa.Column('client_ip', sa.String(length=45), nullable=True))
    op.add_column('export_jobs', sa.Column('columns', sa.String(length=255), nullable=True))
    op.add_column('export_jobs', sa.Column('checksum_sha256', sa.String(length=64), nullable=True))
    op.add_column('export_jobs', sa.Column('share_token_hash', sa.String(length=64), nullable=True))
    op.add_column('export_jobs', sa.Column('share_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('export_jobs', sa.Column('share_created_by', sa.String(length=36), nullable=True))
    op.create_index('ix_export_jobs_share_token_hash', 'export_jobs', ['share_token_hash'])


def downgrade() -> None:
    op.drop_index('ix_export_jobs_share_token_hash', table_name='export_jobs')
    op.drop_column('export_jobs', 'share_created_by')
    op.drop_column('export_jobs', 'share_token_expires_at')
    op.drop_column('export_jobs', 'share_token_hash')
    op.drop_column('export_jobs', 'checksum_sha256')
    op.drop_column('export_jobs', 'columns')
    op.drop_column('export_jobs', 'client_ip')
    op.drop_column('export_jobs', 'category')
    op.drop_column('export_jobs', 'domain')
