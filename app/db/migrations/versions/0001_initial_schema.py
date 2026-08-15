"""initial schema: sources, chunks, footnotes

Revision ID: 0001
Revises:
Create Date: 2026-08-15

"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Must match app.api.models.chunk.EMBEDDING_DIM.
EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("edition", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("pdf_object_key", sa.Text(), nullable=False),
        sa.Column("pdf_pages_total", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_type in ('commentary', 'textbook')", name="ck_sources_source_type"),
    )
    op.create_index("ix_sources_jurisdiction", "sources", ["jurisdiction"])

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("point_number", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("hierarchy", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("concept_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True, server_default="{}"),
        sa.Column(
            "text_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index("ix_chunks_text_tsv", "chunks", ["text_tsv"], postgresql_using="gin")
    # HNSW index for cosine-similarity nearest-neighbor search; created with
    # plain CREATE INDEX (not CONCURRENTLY) since the table is empty at
    # deploy time and migrations run inside a transaction.
    op.execute("CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "footnotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_footnotes_chunk_id", "footnotes", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("footnotes")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_chunks_text_tsv", table_name="chunks")
    op.drop_index("ix_chunks_source_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_sources_jurisdiction", table_name="sources")
    op.drop_table("sources")
