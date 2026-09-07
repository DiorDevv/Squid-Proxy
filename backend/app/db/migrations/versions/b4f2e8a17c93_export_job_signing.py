"""export job signing (manifest + Ed25519 signature)

Revision ID: b4f2e8a17c93
Revises: d7e2a9c4f318
Create Date: 2026-09-04 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4f2e8a17c93"
down_revision: str | None = "d7e2a9c4f318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("manifest_json", sa.Text(), nullable=True))
    op.add_column("export_jobs", sa.Column("signature_b64", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "signature_b64")
    op.drop_column("export_jobs", "manifest_json")
