"""super admin role, username login, user lifecycle fields, sessions

One logical change (super-admin user management, see
app/services/user_service.py):
  - userrole gains SUPERADMIN; every *unrestricted* admin (branch IS NULL)
    becomes a super admin, branch-scoped admins stay admins.
  - users: username (the login name, backfilled from the email's local
    part), email becomes optional, plus full_name/note/is_active/
    must_change_password/password_changed_at/last_login_at/last_login_ip/
    created_by/updated_at.
  - password_history for the no-reuse rule.
  - refresh_tokens: session_id (one per sign-in, carried across rotation),
    ip/user_agent/session_started_at/last_seen_at, and reauth_at.
  - auditaction gains the new user-management actions.

Revision ID: c3a7f1e9d2b4
Revises: b7e2f9a4c815
Create Date: 2026-10-13 12:00:00.000000

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a7f1e9d2b4"
down_revision: str | None = "b7e2f9a4c815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_OLD = ("ADMIN", "VIEWER", "AUDITOR")
_ROLE_NEW = ("SUPERADMIN", *_ROLE_OLD)

_ACTION_NEW_VALUES = (
    "USER_UPDATED",
    "USER_DEACTIVATED",
    "USER_ACTIVATED",
    "USER_UNLOCKED",
    "USER_SESSIONS_REVOKED",
    "USER_PASSWORD_CHANGED",
    "USER_TOTP_RESET",
)
_ACTION_OLD = (
    "USER_CREATED",
    "USER_ROLE_CHANGED",
    "USER_PASSWORD_RESET",
    "USER_DELETED",
    "EXPORT_CREATED",
    "EXPORT_DOWNLOADED",
    "EXPORT_SHARED",
    "ALERT_SETTINGS_UPDATED",
    "DOMAIN_CATEGORY_SET",
    "DOMAIN_CATEGORY_IMPORTED",
    "EXPORT_SETTINGS_UPDATED",
    "EXPORT_CANCELLED",
    "EXPORT_SHARE_REVOKED",
    "REPORT_SENT_NOW",
    "USER_BRANCH_CHANGED",
    "TOTP_ENABLED",
    "TOTP_DISABLED",
    "TOTP_RECOVERY_CODE_USED",
    "TELEGRAM_LINKED",
    "CLIENT_ACTIVITY_VIEWED",
    "EVENT_SEARCH_RUN",
    "ANALYTICS_ACTOR_VIEWED",
    "SUBJECT_DOSSIER_EXPORTED",
    "RETENTION_SETTINGS_UPDATED",
    "ALERT_RULE_CREATED",
    "ALERT_RULE_UPDATED",
    "ALERT_RULE_DELETED",
)
_ACTION_ALL = _ACTION_OLD + _ACTION_NEW_VALUES

# Mirrors app/core/password_policy.USERNAME_RE / RESERVED_USERNAMES, frozen
# here so this migration keeps producing the same result if those change.
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_RESERVED = {"anonymous", "system", "root", "unknown", "tizim"}


def _username_from_email(email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]+", ".", email.split("@", 1)[0].lower())
    base = re.sub(r"^[^a-z0-9]+", "", base)[:56]
    if len(base) < 3 or base in _RESERVED:
        base = f"user.{base}".rstrip(".")[:56]
    return base


def _backfill_usernames(bind: sa.engine.Connection) -> None:
    users = sa.table(
        "users", sa.column("id", sa.String), sa.column("email", sa.String), sa.column("username")
    )
    rows = bind.execute(sa.select(users.c.id, users.c.email).order_by(users.c.id)).all()
    taken: set[str] = set()
    for user_id, email in rows:
        base = _username_from_email(email or "user")
        candidate, n = base, 2
        while candidate in taken or not _USERNAME_RE.match(candidate):
            candidate = f"{base}-{n}"
            n += 1
        taken.add(candidate)
        bind.execute(sa.update(users).where(users.c.id == user_id).values(username=candidate))


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # ADD VALUE must be committed before the UPDATE below can use the new
        # role, hence the autocommit block (see 21794ca3a016 for why it's one
        # statement per value).
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'SUPERADMIN'")
            for value in _ACTION_NEW_VALUES:
                op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("full_name", sa.String(length=120), nullable=False, server_default=""))
    op.add_column("users", sa.Column("note", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(
        "users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_ip", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("created_by", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    _backfill_usernames(bind)

    if is_pg:
        op.alter_column("users", "username", existing_type=sa.String(length=64), nullable=False)
        op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("username", existing_type=sa.String(length=64), nullable=False)
            batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=True)
            batch_op.alter_column(
                "role",
                type_=sa.Enum(*_ROLE_NEW, name="userrole"),
                existing_type=sa.Enum(*_ROLE_OLD, name="userrole"),
                existing_nullable=False,
            )
        with op.batch_alter_table("audit_log_entries") as batch_op:
            batch_op.alter_column(
                "action",
                type_=sa.Enum(*_ACTION_ALL, name="auditaction"),
                existing_type=sa.Enum(*_ACTION_OLD, name="auditaction"),
                existing_nullable=False,
            )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    # Unrestricted admins were the de-facto super admins (the only ones who
    # could manage other admins or the super-admin Telegram chat).
    op.execute("UPDATE users SET role = 'SUPERADMIN' WHERE role = 'ADMIN' AND branch IS NULL")

    op.create_table(
        "password_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_password_history_user_id"), "password_history", ["user_id"], unique=False)

    op.add_column("refresh_tokens", sa.Column("session_id", sa.String(length=36), nullable=True))
    op.add_column("refresh_tokens", sa.Column("ip", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.String(length=255), nullable=True))
    op.add_column(
        "refresh_tokens", sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("refresh_tokens", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("reauth_at", sa.DateTime(timezone=True), nullable=True))
    # Each pre-existing token becomes its own session.
    op.execute(
        "UPDATE refresh_tokens SET session_id = jti, session_started_at = created_at, last_seen_at = created_at"
    )
    with op.batch_alter_table("refresh_tokens") as batch_op:
        batch_op.alter_column("session_id", existing_type=sa.String(length=36), nullable=False)
    op.create_index(op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        raise NotImplementedError("Cannot downgrade: Postgres doesn't support removing enum values.")

    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    with op.batch_alter_table("refresh_tokens") as batch_op:
        for column in ("reauth_at", "last_seen_at", "session_started_at", "user_agent", "ip", "session_id"):
            batch_op.drop_column(column)

    op.drop_index(op.f("ix_password_history_user_id"), table_name="password_history")
    op.drop_table("password_history")

    op.execute("UPDATE users SET role = 'ADMIN' WHERE role = 'SUPERADMIN'")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    with op.batch_alter_table("audit_log_entries") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_ACTION_OLD, name="auditaction"),
            existing_type=sa.Enum(*_ACTION_ALL, name="auditaction"),
            existing_nullable=False,
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "role",
            type_=sa.Enum(*_ROLE_OLD, name="userrole"),
            existing_type=sa.Enum(*_ROLE_NEW, name="userrole"),
            existing_nullable=False,
        )
        # Fails loudly if a user without an email was created since -- such an
        # account can't exist in the old schema.
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=False)
        for column in (
            "updated_at",
            "created_by",
            "last_login_ip",
            "last_login_at",
            "password_changed_at",
            "must_change_password",
            "is_active",
            "note",
            "full_name",
            "username",
        ):
            batch_op.drop_column(column)
