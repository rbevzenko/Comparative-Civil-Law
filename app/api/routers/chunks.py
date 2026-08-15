import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.database import get_db
from app.api.models.chunk import Chunk
from app.api.models.source import Source
from app.api.schemas.chunk import ChunkBulkCreate, ChunkDetail, ChunkList, ChunkRead
from app.api.security import require_api_token
from app.api.services.chunks import create_chunks as create_chunks_records

# Bulk upload / listing scoped to a source — used by the normalization
# pipeline that turns a parsed PDF into chunks.
source_chunks_router = APIRouter(
    prefix="/sources/{source_id}/chunks",
    tags=["chunks"],
    dependencies=[Depends(require_api_token)],
)

# Fetching a single chunk by id — the shape the future MCP wrapper needs.
chunks_router = APIRouter(prefix="/chunks", tags=["chunks"], dependencies=[Depends(require_api_token)])


async def _get_source_or_404(source_id: uuid.UUID, db: AsyncSession) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


@source_chunks_router.post("", response_model=ChunkList, status_code=status.HTTP_201_CREATED)
async def create_chunks(
    source_id: uuid.UUID,
    payload: ChunkBulkCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChunkList:
    await _get_source_or_404(source_id, db)
    created = await create_chunks_records(db, source_id, payload.chunks)
    return ChunkList(items=[ChunkRead.model_validate(c) for c in created], total=len(created))


@source_chunks_router.get("", response_model=ChunkList)
async def list_source_chunks(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> ChunkList:
    await _get_source_or_404(source_id, db)

    stmt = (
        select(Chunk)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.page_start.nulls_last(), Chunk.created_at)
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt)).scalars().all()
    return ChunkList(items=[ChunkRead.model_validate(c) for c in rows], total=total)


@chunks_router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> Chunk:
    stmt = (
        select(Chunk)
        .where(Chunk.id == chunk_id)
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    chunk = (await db.execute(stmt)).scalar_one_or_none()
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk
