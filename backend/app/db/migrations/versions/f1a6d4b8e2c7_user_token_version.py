"""user token_version for immediate session invalidation

Revision ID: f1a6d4b8e2c7
Revises: e9a3c7f1b562
Create Date: 2026-09-07 12:00:00.000000

A monotonically increasing per-user counter stamped into every access
token as the `tv` claim. get_current_user rejects a token whose `tv`
doesn't match the live row, so bumping this (on a role/branch change or a
password reset -- see app/services/user_service.py) logs every existing
session of that user out at once, rather than leaving stale tokens valid
for the full ACCESS_TOKEN_EXPIRE_MINUTES window. Starts at 1; a token
minted before this column existed carries no `tv` and is grandfathered
(checked for the user still existing, but not for a version match) -- those
all age out within one access-token lifetime.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a6d4b8e2c7"
down_revision: str | None = "e9a3c7f1b562"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("token_version")
