"""export jobs

Revision ID: 5f19c6b8d4a7
Revises: 094a3d323ab2
Create Date: 2026-07-21 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5f19c6b8d4a7'
down_revision: str | None = '094a3d323ab2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'export_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'DONE', 'FAILED', name='exportjobstatus'),
            nullable=False,
        ),
        sa.Column('format', sa.String(length=8), nullable=False),
        sa.Column('since', sa.DateTime(timezone=True), nullable=False),
        sa.Column('until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('blocked_only', sa.Boolean(), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_export_jobs_status', 'export_jobs', ['status'])
    op.create_index('ix_export_jobs_created_at', 'export_jobs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_export_jobs_created_at', table_name='export_jobs')
    op.drop_index('ix_export_jobs_status', table_name='export_jobs')
    op.drop_table('export_jobs')
    op.execute('DROP TYPE IF EXISTS exportjobstatus')
