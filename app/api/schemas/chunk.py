import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.api.models.chunk import EMBEDDING_DIM
from app.api.schemas.footnote import FootnoteCreate, FootnoteRead
from app.api.schemas.source import SourceRead
from app.api.security import build_universal_ref


class ChunkCreate(BaseModel):
    # Stable id from the external normalization pipeline. Optional, but
    # strongly recommended: when set, re-uploading the same file for this
    # source updates the matching chunks instead of duplicating them.
    external_id: str | None = None
    citation: str
    point_number: str | None = None
    text: str
    hierarchy: list[str] = Field(default_factory=list)
    # Pages of the source FILE.
    page_start: int | None = None
    page_end: int | None = None
    # Pages of the PRINTED edition — the pair a reader may cite. Optional:
    # files without a folio (Westlaw exports, most e-books) leave them unset.
    printed_page_start: int | None = None
    printed_page_end: int | None = None
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
    external_id: str | None
    citation: str
    point_number: str | None
    text: str
    hierarchy: list
    page_start: int | None
    page_end: int | None
    printed_page_start: int | None
    printed_page_end: int | None
    concept_ids: list[uuid.UUID] | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def universal_ref(self) -> str | None:
        """Public, citable link to this fragment — show it next to every
        quote pulled from this chunk (see app.web.router's /source route)."""
        return build_universal_ref(self.id)


class ChunkDetail(ChunkRead):
    footnotes: list[FootnoteRead] = Field(default_factory=list)
    source: SourceRead | None = None


class ChunkList(BaseModel):
    items: list[ChunkRead]
    total: int
