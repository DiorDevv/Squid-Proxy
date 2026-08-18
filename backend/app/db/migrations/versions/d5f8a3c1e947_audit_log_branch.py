"""audit log entry branch scoping

Revision ID: d5f8a3c1e947
Revises: a228da90977c
Create Date: 2026-08-18 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5f8a3c1e947'
down_revision: str | None = 'a228da90977c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: existing rows predate branch-scoping and become
    # NULL, which app.services.audit_service.list_entries already treats as
    # "not confined to one branch" -- i.e. still visible to everyone, the
    # same as today's unscoped behavior, rather than needing a backfill.
    op.add_column('audit_log_entries', sa.Column('branch', sa.String(length=64), nullable=True))
    op.create_index('ix_audit_log_entries_branch', 'audit_log_entries', ['branch'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_entries_branch', table_name='audit_log_entries')
    op.drop_column('audit_log_entries', 'branch')
