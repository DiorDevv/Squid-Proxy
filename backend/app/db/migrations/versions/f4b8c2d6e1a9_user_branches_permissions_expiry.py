"""users: several branches, feature permissions, access end date

`users.branch` (one tag or NULL) becomes `users.branches` (a JSON list or
NULL = unrestricted); every existing single branch carries over as a
one-element list. Adds `users.permissions` (NULL = the role's defaults) and
`users.expires_at` (NULL = no end date).

Downgrade keeps the first branch of a multi-branch account -- narrower, never
wider, than what it had.

Revision ID: f4b8c2d6e1a9
Revises: e5c1a8f3b27d
Create Date: 2026-10-14 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b8c2d6e1a9"
down_revision: str | None = "e5c1a8f3b27d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("branches", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("permissions", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, branch FROM users WHERE branch IS NOT NULL")).all()
    for user_id, branch in rows:
        bind.execute(
            sa.text("UPDATE users SET branches = :branches WHERE id = :id").bindparams(
                sa.bindparam("branches", type_=sa.JSON())
            ),
            {"branches": [branch], "id": user_id},
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("branch")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("branch", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, branches FROM users WHERE branches IS NOT NULL")).all()
    for user_id, branches in rows:
        if isinstance(branches, str):
            branches = json.loads(branches)
        if branches:
            bind.execute(
                sa.text("UPDATE users SET branch = :branch WHERE id = :id"),
                {"branch": sorted(branches)[0], "id": user_id},
            )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("expires_at")
        batch_op.drop_column("permissions")
        batch_op.drop_column("branches")
