from pydantic import BaseModel, Field

from app.api.schemas.chunk import ChunkDetail


class SearchRequest(BaseModel):
    q: str = ""
    jurisdiction: str | None = None
    source_type: str | None = None
    # Optional precomputed query embedding for the vector half of hybrid
    # search. Same rationale as chunk writes: the API never calls an
    # embedding model itself — the caller (MCP server / normalization
    # script) computes it with whatever model matches the corpus embeddings.
    # Omit it for lexical-only (full-text) search.
    embedding: list[float] | None = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SearchResultItem(BaseModel):
    chunk: ChunkDetail
    score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None


class SearchResponse(BaseModel):
    query: str
    items: list[SearchResultItem]
    total: int
