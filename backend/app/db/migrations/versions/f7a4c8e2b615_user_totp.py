"""user totp secret/enabled and recovery codes table

Revision ID: f7a4c8e2b615
Revises: e2c6a1d9f453
Create Date: 2026-08-21 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7a4c8e2b615'
down_revision: str | None = 'e2c6a1d9f453'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('totp_secret', sa.String(length=64), nullable=True))
    op.add_column(
        'users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table(
        'totp_recovery_codes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_totp_recovery_codes_user_id', 'totp_recovery_codes', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_totp_recovery_codes_user_id', table_name='totp_recovery_codes')
    op.drop_table('totp_recovery_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
