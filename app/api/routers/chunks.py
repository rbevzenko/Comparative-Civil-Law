import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.database import get_db
from app.api.models.chunk import Chunk
from app.api.models.source import Source
from app.api.schemas.chunk import (
    ChunkBulkCreate,
    ChunkBulkPatch,
    ChunkDetail,
    ChunkDetailList,
    ChunkList,
    ChunkPatch,
    ChunkPatchResult,
    ChunkRead,
    ChunkWithFootnotes,
)
from app.api.security import require_api_token
from app.api.services.chunks import create_chunks as create_chunks_records
from app.api.services.chunks import get_chunk as get_chunk_record
from app.api.services.chunks import patch_chunk as patch_chunk_record
from app.api.services.chunks import patch_chunks_by_external_id

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


# response_model=None намеренно: ответов у маршрута два, и объединение в
# response_model заставило бы FastAPI выбирать между ними — при выборе
# ChunkList сноски молча отвалились бы. Оба ответа и так модели pydantic,
# сериализуются они одинаково.
@source_chunks_router.get("", response_model=None)
async def list_source_chunks(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
    with_footnotes: bool = False,
) -> ChunkList | ChunkDetailList:
    """with_footnotes отдаёт сноски вместе с чанком.

    Нужно для обратной выгрузки: чтобы перезалить исправленный текст, надо
    отдать чанк целиком — приём заменяет набор сносок целиком, и чанк,
    посланный без них, свои сноски теряет. Поштучный GET /chunks/{id} на
    тридцать тысяч чанков — тридцать тысяч запросов, поэтому сноски
    отдаются страницей.
    """
    await _get_source_or_404(source_id, db)

    stmt = (
        select(Chunk)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.page_start.nulls_last(), Chunk.created_at)
        .limit(limit)
        .offset(offset)
    )
    if with_footnotes:
        stmt = stmt.options(selectinload(Chunk.footnotes))
    count_stmt = select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt)).scalars().all()
    if with_footnotes:
        return ChunkDetailList(items=[ChunkWithFootnotes.model_validate(c) for c in rows], total=total)
    return ChunkList(items=[ChunkRead.model_validate(c) for c in rows], total=total)


@source_chunks_router.patch("", response_model=ChunkPatchResult)
async def patch_source_chunks(
    source_id: uuid.UUID,
    payload: ChunkBulkPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChunkPatchResult:
    """Пакетная правка реквизитов чанков источника, адресация по external_id.

    Ради этого маршрута всё и делалось: дозалить в уже загруженный корпус
    номера печатных страниц, не считая заново ни одного эмбеддинга. Текст
    и вектор PATCH не трогает вовсе (см. ChunkPatch), поэтому правка
    безопасна для поиска и не меняет выданные наружу universal_ref.
    """
    await _get_source_or_404(source_id, db)
    updated, unchanged, missing = await patch_chunks_by_external_id(db, source_id, payload.chunks)
    return ChunkPatchResult(updated=updated, unchanged=unchanged, missing=missing)


@chunks_router.patch("/{chunk_id}", response_model=ChunkDetail)
async def patch_chunk(
    chunk_id: uuid.UUID,
    payload: ChunkPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Chunk:
    """Точечная правка одного чанка — руками, из карточки фрагмента."""
    chunk = await patch_chunk_record(db, chunk_id, payload.changes())
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk


@chunks_router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> Chunk:
    chunk = await get_chunk_record(db, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk
