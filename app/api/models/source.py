import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.api.models.base import Base

if TYPE_CHECKING:
    from app.api.models.chunk import Chunk


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("source_type in ('commentary', 'textbook')", name="ck_sources_source_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    jurisdiction: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    edition: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Path/key of the PDF inside the S3-compatible object storage bucket.
    # The raw file is never served through the API — only presigned URLs.
    pdf_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_pages_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="source", cascade="all, delete-orphan")
