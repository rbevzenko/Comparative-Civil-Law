import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.database import get_db
from app.api.models.chunk import Chunk
from app.api.models.source import Source
from app.api.storage import generate_presigned_url
from app.web.auth import require_basic_auth

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

router = APIRouter(prefix="/ui", tags=["web"], dependencies=[Depends(require_basic_auth)])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
async def ui_root() -> RedirectResponse:
    return RedirectResponse(url="/ui/sources")


@router.get("/sources")
async def ui_sources(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    jurisdiction: str | None = None,
):
    stmt = select(Source).order_by(Source.jurisdiction, Source.title)
    if jurisdiction:
        stmt = stmt.where(Source.jurisdiction == jurisdiction)
    sources = (await db.execute(stmt)).scalars().all()

    all_jurisdictions_rows = (await db.execute(select(Source.jurisdiction).distinct())).scalars().all()
    jurisdictions = sorted(set(all_jurisdictions_rows))

    return templates.TemplateResponse(
        request,
        "sources_list.html",
        {"sources": sources, "jurisdictions": jurisdictions, "selected_jurisdiction": jurisdiction},
    )


@router.get("/sources/{source_id}")
async def ui_source_detail(source_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    source = await db.get(Source, source_id)
    if source is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "источник"}, status_code=404)

    chunks_stmt = (
        select(Chunk).where(Chunk.source_id == source_id).order_by(Chunk.page_start.nulls_last(), Chunk.created_at)
    )
    chunks = (await db.execute(chunks_stmt)).scalars().all()
    pdf_url = generate_presigned_url(source.pdf_object_key)

    return templates.TemplateResponse(
        request, "source_detail.html", {"source": source, "chunks": chunks, "pdf_url": pdf_url}
    )


@router.get("/chunks/{chunk_id}")
async def ui_chunk_detail(chunk_id: uuid.UUID, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = (
        select(Chunk)
        .where(Chunk.id == chunk_id)
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    chunk = (await db.execute(stmt)).scalar_one_or_none()
    if chunk is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "чанк"}, status_code=404)

    pdf_url = generate_presigned_url(chunk.source.pdf_object_key) if chunk.source else None

    return templates.TemplateResponse(request, "chunk_detail.html", {"chunk": chunk, "pdf_url": pdf_url})
