"""add uncategorized_domain_request_threshold to alert_settings

Revision ID: e1f4a7c2b9d5
Revises: 6d1f9b3c8a52
Create Date: 2026-07-28 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1f4a7c2b9d5'
down_revision: str | None = '6d1f9b3c8a52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default -- None means "off", matching
    # client_daily_byte_quota_bytes's existing opt-in convention rather than
    # a nonzero default that would start flagging domains on every
    # deployment without an admin ever having asked for it.
    op.add_column(
        'alert_settings', sa.Column('uncategorized_domain_request_threshold', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('alert_settings', 'uncategorized_domain_request_threshold')
