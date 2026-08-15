import uuid
from typing import BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models.source import Source
from app.api.storage import build_object_key, upload_pdf

ALLOWED_SOURCE_TYPES = {"commentary", "textbook"}


class InvalidSourceUpload(ValueError):
    """Raised for user-input problems (bad source_type, non-PDF file, ...)."""


async def create_source(
    db: AsyncSession,
    *,
    title: str,
    jurisdiction: str,
    source_type: str,
    authors_raw: str,
    edition: str | None,
    year: int | None,
    publisher: str | None,
    language: str | None,
    pdf_pages_total: int | None,
    pdf_filename: str | None,
    pdf_content_type: str | None,
    pdf_file: BinaryIO,
) -> Source:
    """Shared by the JSON API (POST /sources) and the /ui/upload/source form."""
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise InvalidSourceUpload(f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}")
    if pdf_content_type not in ("application/pdf", "application/x-pdf"):
        raise InvalidSourceUpload("pdf must be a PDF file")

    author_list = [a.strip() for a in authors_raw.split(";") if a.strip()]

    source_id = uuid.uuid4()
    object_key = build_object_key(source_id, pdf_filename or "source.pdf")
    upload_pdf(object_key, pdf_file, pdf_content_type or "application/pdf")

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
