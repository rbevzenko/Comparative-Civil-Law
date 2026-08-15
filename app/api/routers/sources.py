import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.database import get_db
from app.api.models.source import Source
from app.api.schemas.source import SourceDetail, SourceList, SourceRead
from app.api.security import require_api_token
from app.api.storage import build_object_key, generate_presigned_url, upload_pdf

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_api_token)])

ALLOWED_SOURCE_TYPES = {"commentary", "textbook"}


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
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}",
        )
    if pdf.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pdf must be a PDF file")

    author_list = [a.strip() for a in authors.split(";") if a.strip()]

    source_id = uuid.uuid4()
    object_key = build_object_key(source_id, pdf.filename or "source.pdf")
    upload_pdf(object_key, pdf.file, pdf.content_type or "application/pdf")

    source = Source(
        id=source_id,
        title=title,
        authors=author_list,
        jurisdiction=jurisdiction,
        edition=edition,
        year=year,
        publisher=publisher,
        language=language,
        pdf_object_key=object_key,
        pdf_pages_total=pdf_pages_total,
        source_type=source_type,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


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
