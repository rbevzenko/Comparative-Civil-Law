"""add chunks.external_id with per-source uniqueness

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("external_id", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_chunks_source_external_id", "chunks", ["source_id", "external_id"])


def downgrade() -> None:
    op.drop_constraint("uq_chunks_source_external_id", "chunks", type_="unique")
    op.drop_column("chunks", "external_id")
