import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.database import get_db
from app.api.schemas.search import SearchRequest, SearchResponse
from app.api.security import require_api_token
from app.api.services.search import run_search

router = APIRouter(tags=["search"], dependencies=[Depends(require_api_token)])


async def _run_search(db: AsyncSession, req: SearchRequest) -> SearchResponse:
    try:
        return await run_search(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


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
