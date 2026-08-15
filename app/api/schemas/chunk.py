import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.models.chunk import EMBEDDING_DIM
from app.api.schemas.footnote import FootnoteCreate, FootnoteRead
from app.api.schemas.source import SourceRead


class ChunkCreate(BaseModel):
    citation: str
    point_number: str | None = None
    text: str
    hierarchy: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    # Precomputed by the external normalization pipeline; the API does not
    # generate embeddings itself.
    embedding: list[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    footnotes: list[FootnoteCreate] = Field(default_factory=list)


class ChunkBulkCreate(BaseModel):
    chunks: list[ChunkCreate] = Field(..., min_length=1)


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    citation: str
    point_number: str | None
    text: str
    hierarchy: list
    page_start: int | None
    page_end: int | None
    concept_ids: list[uuid.UUID] | None
    created_at: datetime
    updated_at: datetime


class ChunkDetail(ChunkRead):
    footnotes: list[FootnoteRead] = Field(default_factory=list)
    source: SourceRead | None = None


class ChunkList(BaseModel):
    items: list[ChunkRead]
    total: int
