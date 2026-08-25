"""telegram link codes and global settings

Revision ID: b7e05e34cae1
Revises: f4c9a2e8d716
Create Date: 2026-08-25 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e05e34cae1'
down_revision: str | None = 'f4c9a2e8d716'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_AUDIT_ACTIONS = (
    'USER_CREATED', 'USER_ROLE_CHANGED', 'USER_PASSWORD_RESET', 'USER_DELETED', 'EXPORT_CREATED',
    'EXPORT_DOWNLOADED', 'EXPORT_SHARED', 'ALERT_SETTINGS_UPDATED', 'DOMAIN_CATEGORY_SET',
    'DOMAIN_CATEGORY_IMPORTED', 'EXPORT_SETTINGS_UPDATED', 'EXPORT_CANCELLED', 'EXPORT_SHARE_REVOKED',
    'REPORT_SENT_NOW', 'USER_BRANCH_CHANGED', 'TOTP_ENABLED', 'TOTP_DISABLED', 'TOTP_RECOVERY_CODE_USED',
)
_NEW_AUDIT_ACTIONS = (
    *_OLD_AUDIT_ACTIONS, 'TELEGRAM_LINKED',
)


def upgrade() -> None:
    op.create_table(
        'telegram_link_codes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('target', sa.Enum('BRANCH', 'SUPER_ADMIN', name='telegramlinktarget'), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consumed_chat_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_telegram_link_codes_code', 'telegram_link_codes', ['code'])

    op.create_table(
        'telegram_global_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('super_admin_chat_id', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # See 21794ca3a016_expanded_audit_actions.py for why this is one
        # ALTER TYPE ADD VALUE statement per value.
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'TELEGRAM_LINKED'")
    else:
        # SQLite has no native enum type -- SQLAlchemy emulates one with a
        # CHECK constraint, which can only be changed by recreating the
        # table (what batch mode does under the hood).
        with op.batch_alter_table('audit_log_entries') as batch_op:
            batch_op.alter_column(
                'action',
                type_=sa.Enum(*_NEW_AUDIT_ACTIONS, name='auditaction'),
                existing_type=sa.Enum(*_OLD_AUDIT_ACTIONS, name='auditaction'),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Postgres can't drop enum values without recreating the type;
        # downgrading here would require rewriting every row that used the
        # new value first. No known caller needs this downgrade path,
        # matches d4a1e7b93c5f_domain_category_imported_audit_action.py's
        # own precedent.
        raise NotImplementedError(
            "Cannot remove enum values from a Postgres type without rewriting affected rows first."
        )
    with op.batch_alter_table('audit_log_entries') as batch_op:
        batch_op.alter_column(
            'action',
            type_=sa.Enum(*_OLD_AUDIT_ACTIONS, name='auditaction'),
            existing_type=sa.Enum(*_NEW_AUDIT_ACTIONS, name='auditaction'),
            existing_nullable=False,
        )

    op.drop_table('telegram_global_settings')
    op.drop_index('ix_telegram_link_codes_code', table_name='telegram_link_codes')
    op.drop_table('telegram_link_codes')
    sa.Enum(name='telegramlinktarget').drop(op.get_bind(), checkfirst=True)
