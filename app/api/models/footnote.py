import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.api.models.base import Base

if TYPE_CHECKING:
    from app.api.models.chunk import Chunk


class Footnote(Base):
    __tablename__ = "footnotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    chunk: Mapped["Chunk"] = relationship(back_populates="footnotes")
