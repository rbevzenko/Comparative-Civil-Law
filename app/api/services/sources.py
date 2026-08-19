import uuid
from typing import BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models.source import Source
from app.api.storage import build_object_key, upload_pdf

ALLOWED_SOURCE_TYPES = {"commentary", "textbook"}

# Everything about a source except the PDF itself. The file is deliberately
# not editable here: chunk page numbers point into that exact file, so
# swapping it would silently make every citation in the source wrong. A new
# file means a new source and a re-run of the normalization pipeline.
EDITABLE_FIELDS = (
    "title",
    "authors",
    "jurisdiction",
    "edition",
    "year",
    "publisher",
    "language",
    "pdf_pages_total",
    "source_type",
)


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

    author_list = parse_authors(authors_raw)

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


def parse_authors(raw: str) -> list[str]:
    """Semicolon-separated author names, as typed in the upload/edit forms."""
    return [a.strip() for a in (raw or "").split(";") if a.strip()]


async def update_source(db: AsyncSession, source: Source, changes: dict) -> Source:
    """Edit a source's bibliographic details in place.

    Shared by PATCH /sources/{id} and the /ui/sources/{id}/edit form. Only
    the fields present in `changes` are touched, so a partial API call does
    not blank out the rest of the card.

    The source id is never reissued, which is the point: `universal_ref`
    links already handed out keep resolving, and chunks stay attached.
    """
    unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
    if unknown:
        raise InvalidSourceUpload(f"unknown field(s): {', '.join(unknown)}")

    if "source_type" in changes and changes["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise InvalidSourceUpload(f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}")
    for required in ("title", "jurisdiction"):
        if required in changes and not (changes[required] or "").strip():
            raise InvalidSourceUpload(f"{required} must not be empty")

    for field, value in changes.items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source
