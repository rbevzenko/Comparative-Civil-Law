"""add chunks.printed_page_start / printed_page_end

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

page_start/page_end are pages of the SOURCE FILE. What a reader has to cite
is the page of the printed edition, and the two differ by a shifting offset
(front matter, plates, re-set volumes). The pipeline already reads the folio
off the page; these columns carry it through to the reader.

Both stay nullable: Westlaw exports and some e-books have no printed folio at
all, and "no printed page" must stay distinguishable from "not uploaded yet".
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("printed_page_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("printed_page_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "printed_page_end")
    op.drop_column("chunks", "printed_page_start")
