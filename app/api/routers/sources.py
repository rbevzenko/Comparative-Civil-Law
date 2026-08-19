import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.database import get_db
from app.api.models.source import Source
from app.api.schemas.source import SourceDetail, SourceList, SourceRead, SourceUpdate
from app.api.security import require_api_token
from app.api.services.sources import InvalidSourceUpload
from app.api.services.sources import create_source as create_source_record
from app.api.services.sources import update_source as update_source_record
from app.api.storage import generate_presigned_url

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_api_token)])


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    title: Annotated[str, Form()],
    jurisdiction: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    pdf: Annotated[UploadFile, File()],
    authors: Annotated[str, Form(description="Semicolon-separated author names")] = "",
    edition: Annotated[str | None, Form()] = None,
    year: Annotated[int | None, Form()] = None,
    publisher: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    pdf_pages_total: Annotated[int | None, Form()] = None,
) -> Source:
    try:
        return await create_source_record(
            db,
            title=title,
            jurisdiction=jurisdiction,
            source_type=source_type,
            authors_raw=authors,
            edition=edition,
            year=year,
            publisher=publisher,
            language=language,
            pdf_pages_total=pdf_pages_total,
            pdf_filename=pdf.filename,
            pdf_content_type=pdf.content_type,
            pdf_file=pdf.file,
        )
    except InvalidSourceUpload as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("", response_model=SourceList)
async def list_sources(
    db: Annotated[AsyncSession, Depends(get_db)],
    jurisdiction: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SourceList:
    stmt = select(Source)
    count_stmt = select(func.count()).select_from(Source)
    if jurisdiction:
        stmt = stmt.where(Source.jurisdiction == jurisdiction)
        count_stmt = count_stmt.where(Source.jurisdiction == jurisdiction)
    if source_type:
        stmt = stmt.where(Source.source_type == source_type)
        count_stmt = count_stmt.where(Source.source_type == source_type)
    stmt = stmt.order_by(Source.jurisdiction, Source.title).limit(limit).offset(offset)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt)).scalars().all()
    return SourceList(items=list(rows), total=total)


@router.get("/{source_id}", response_model=SourceDetail)
async def get_source(source_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> SourceDetail:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    detail = SourceDetail.model_validate(source)
    detail.pdf_url = generate_presigned_url(source.pdf_object_key)
    return detail


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Source:
    """Edit a source's bibliographic details. The PDF is not replaceable —
    chunk page numbers point into that exact file."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return source
    try:
        return await update_source_record(db, source, changes)
    except InvalidSourceUpload as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
