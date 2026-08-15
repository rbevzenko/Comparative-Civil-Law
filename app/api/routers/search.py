import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.database import get_db
from app.api.models.chunk import Chunk
from app.api.models.source import Source
from app.api.schemas.chunk import ChunkDetail
from app.api.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.api.security import require_api_token

router = APIRouter(tags=["search"], dependencies=[Depends(require_api_token)])

# Reciprocal Rank Fusion: combines the lexical and vector candidate rankings
# without needing to normalize ts_rank scores against cosine distances,
# which live on unrelated scales. k=60 is the constant from the original
# RRF paper (Cormack et al.) and is not sensitive to tuning here.
RRF_K = 60
LEXICAL_CANDIDATES = 100
VECTOR_CANDIDATES = 100


async def _run_search(db: AsyncSession, req: SearchRequest) -> SearchResponse:
    if not req.q.strip() and not req.embedding:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least a non-empty q (lexical) or an embedding (vector) to search on",
        )

    base_stmt = select(Chunk.id).join(Source, Chunk.source_id == Source.id)
    if req.jurisdiction:
        base_stmt = base_stmt.where(Source.jurisdiction == req.jurisdiction)
    if req.source_type:
        base_stmt = base_stmt.where(Source.source_type == req.source_type)

    lexical_ranks: dict[uuid.UUID, int] = {}
    vector_ranks: dict[uuid.UUID, int] = {}

    if req.q.strip():
        tsquery = func.plainto_tsquery("simple", req.q)
        lex_stmt = (
            base_stmt.where(Chunk.text_tsv.op("@@")(tsquery))
            .order_by(func.ts_rank(Chunk.text_tsv, tsquery).desc())
            .limit(LEXICAL_CANDIDATES)
        )
        rows = (await db.execute(lex_stmt)).scalars().all()
        lexical_ranks = {cid: rank for rank, cid in enumerate(rows, start=1)}

    if req.embedding:
        vec_stmt = base_stmt.order_by(Chunk.embedding.cosine_distance(req.embedding)).limit(VECTOR_CANDIDATES)
        rows = (await db.execute(vec_stmt)).scalars().all()
        vector_ranks = {cid: rank for rank, cid in enumerate(rows, start=1)}

    combined: dict[uuid.UUID, float] = {}
    for cid, rank in lexical_ranks.items():
        combined[cid] = combined.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    for cid, rank in vector_ranks.items():
        combined[cid] = combined.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    ordered_ids = sorted(combined, key=lambda cid: combined[cid], reverse=True)
    page_ids = ordered_ids[req.offset : req.offset + req.limit]

    if not page_ids:
        return SearchResponse(query=req.q, items=[], total=len(ordered_ids))

    detail_stmt = (
        select(Chunk)
        .where(Chunk.id.in_(page_ids))
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    chunk_rows = (await db.execute(detail_stmt)).scalars().all()
    chunks_by_id = {c.id: c for c in chunk_rows}

    items = [
        SearchResultItem(
            chunk=ChunkDetail.model_validate(chunks_by_id[cid]),
            score=combined[cid],
            lexical_rank=lexical_ranks.get(cid),
            vector_rank=vector_ranks.get(cid),
        )
        for cid in page_ids
        if cid in chunks_by_id
    ]
    return SearchResponse(query=req.q, items=items, total=len(ordered_ids))


@router.get("/search", response_model=SearchResponse)
async def search_get(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query("", description="Lexical query text"),
    jurisdiction: str | None = None,
    source_type: str | None = None,
    embedding: str | None = Query(
        None,
        description=(
            "Optional precomputed query embedding as a JSON array of floats, e.g. [0.01,-0.2,...]. "
            "Adds the vector half of hybrid search; omit for lexical-only search. "
            "A real embedding is long — prefer POST /search for it, GET exists mainly for short/lexical queries."
        ),
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    parsed_embedding: list[float] | None = None
    if embedding:
        try:
            parsed_embedding = json.loads(embedding)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="embedding must be a JSON array of floats"
            ) from exc

    req = SearchRequest(
        q=q,
        jurisdiction=jurisdiction,
        source_type=source_type,
        embedding=parsed_embedding,
        limit=limit,
        offset=offset,
    )
    return await _run_search(db, req)


@router.post("/search", response_model=SearchResponse)
async def search_post(req: SearchRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> SearchResponse:
    return await _run_search(db, req)
