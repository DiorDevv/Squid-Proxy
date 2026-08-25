"""alert settings telegram chat id

Revision ID: f4c9a2e8d716
Revises: d4a1e7b93c5f
Create Date: 2026-08-25 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4c9a2e8d716'
down_revision: str | None = 'd4a1e7b93c5f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('alert_settings') as batch_op:
        batch_op.add_column(sa.Column('telegram_chat_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('alert_settings') as batch_op:
        batch_op.drop_column('telegram_chat_id')
