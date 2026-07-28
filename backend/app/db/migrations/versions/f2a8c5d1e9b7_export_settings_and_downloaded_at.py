"""add export_settings table and export_jobs.downloaded_at

Revision ID: f2a8c5d1e9b7
Revises: e1f4a7c2b9d5
Create Date: 2026-07-28 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2a8c5d1e9b7'
down_revision: str | None = 'e1f4a7c2b9d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('export_jobs', sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_export_jobs_downloaded_at', 'export_jobs', ['downloaded_at'])

    op.create_table(
        'export_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'cleanup_mode',
            sa.Enum('TIME_BASED', 'AFTER_DOWNLOAD', name='exportcleanupmode'),
            nullable=False,
        ),
        sa.Column('retention_hours', sa.Integer(), nullable=False),
        sa.Column('warn_undownloaded_after_hours', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('export_settings')
    # Postgres enums are a separate catalog object, not dropped by
    # drop_table alone.
    sa.Enum(name='exportcleanupmode').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_export_jobs_downloaded_at', table_name='export_jobs')
    op.drop_column('export_jobs', 'downloaded_at')
