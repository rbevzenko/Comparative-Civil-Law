import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Computed, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.api.models.base import Base

if TYPE_CHECKING:
    from app.api.models.footnote import Footnote
    from app.api.models.source import Source

# Embedding dimensionality is fixed at the database schema level, because
# pgvector's HNSW index requires a static vector size for a given column.
# 1536 matches OpenAI text-embedding-3-small / text-embedding-ada-002, a
# reasonable default for the normalization pipeline that will compute these
# vectors externally. If a different embedding model is chosen later, this
# constant and the migration that defines the `embedding` column (and its
# HNSW index) must be updated together.
EMBEDDING_DIM = 1536


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_chunks_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Stable id from the external normalization pipeline (e.g. the chunker's
    # own "book_id-unit" key). Optional, but when present it lets re-uploading
    # the same normalization output update existing chunks for this source
    # instead of duplicating them — see app.api.services.chunks.create_chunks.
    # NULL is excluded from the unique constraint by Postgres, so chunks
    # without one never collide with each other.
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    point_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    hierarchy: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Computed externally by the normalization pipeline and supplied as-is on
    # write; the API never calls an embedding model itself.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # Placeholder for the future glossary/concept layer; empty until that
    # work lands.
    concept_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list
    )
    # Generated column backing the lexical (full-text) half of /search.
    # "simple" config is used deliberately: the corpus spans many languages
    # (French, German, Dutch, Italian, Spanish, English, Greek...) and a
    # single stemmed config would be wrong for most of them.
    text_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source: Mapped["Source"] = relationship(back_populates="chunks")
    footnotes: Mapped[list["Footnote"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", order_by="Footnote.number"
    )
