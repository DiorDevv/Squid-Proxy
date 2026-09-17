"""audit log tamper-evidence hash chain

Revision ID: a2f9c7e4b1d8
Revises: f1a6d4b8e2c7
Create Date: 2026-09-07 13:00:00.000000

Adds prev_hash / entry_hash to audit_log_entries and backfills the chain
over any rows that already exist, in (created_at, id) order -- the same
order audit_service.verify_chain walks. Uses the app's own
compute_entry_hash so a backfilled row and a row written after this
migration hash identically (a divergence would make the chain look broken
exactly at the cutover).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.audit_service import compute_entry_hash

# revision identifiers, used by Alembic.
revision: str = "a2f9c7e4b1d8"
down_revision: str | None = "f1a6d4b8e2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log_entries") as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("entry_hash", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_audit_log_entries_entry_hash", ["entry_hash"], unique=False)

    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT id, created_at, action, branch, actor_user_id, actor_email, "
                "target_user_id, target_email, detail "
                "FROM audit_log_entries ORDER BY created_at ASC, id ASC"
            )
        )
        .mappings()
        .all()
    )

    prev_hash: str | None = None
    for row in rows:
        entry_hash = compute_entry_hash(
            prev_hash=prev_hash,
            entry_id=row["id"],
            created_at=row["created_at"],
            action=row["action"],
            branch=row["branch"],
            actor_user_id=row["actor_user_id"],
            actor_email=row["actor_email"],
            target_user_id=row["target_user_id"],
            target_email=row["target_email"],
            detail=row["detail"],
        )
        bind.execute(
            sa.text("UPDATE audit_log_entries SET prev_hash = :prev, entry_hash = :cur WHERE id = :id"),
            {"prev": prev_hash, "cur": entry_hash, "id": row["id"]},
        )
        prev_hash = entry_hash


def downgrade() -> None:
    with op.batch_alter_table("audit_log_entries") as batch_op:
        batch_op.drop_index("ix_audit_log_entries_entry_hash")
        batch_op.drop_column("entry_hash")
        batch_op.drop_column("prev_hash")
