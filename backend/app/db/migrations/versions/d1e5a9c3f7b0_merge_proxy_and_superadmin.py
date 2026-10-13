"""merge the source-proxy and super-admin migration branches

Both c4d8e1f7a392 (proxy column) and c3a7f1e9d2b4 (super-admin user
management) were written on top of b7e2f9a4c815 on separate branches. They
touch unrelated tables, so this only joins the two heads -- whichever one a
database already has applied, `alembic upgrade head` applies the other.

Revision ID: d1e5a9c3f7b0
Revises: c4d8e1f7a392, c3a7f1e9d2b4
Create Date: 2026-10-13 08:00:00.000000
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d1e5a9c3f7b0"
down_revision: str | Sequence[str] | None = ("c4d8e1f7a392", "c3a7f1e9d2b4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
