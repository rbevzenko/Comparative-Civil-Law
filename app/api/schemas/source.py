import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal["commentary", "textbook"]


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: list[str]
    jurisdiction: str
    edition: str | None
    year: int | None
    publisher: str | None
    language: str | None
    pdf_pages_total: int | None
    source_type: SourceType
    created_at: datetime
    updated_at: datetime


class SourceUpdate(BaseModel):
    """Partial edit of a source card. Every field is optional and only the
    ones actually sent are applied — `model_dump(exclude_unset=True)` is what
    separates "leave as is" from "set to null", which a plain None cannot."""

    title: str | None = None
    authors: list[str] | None = None
    jurisdiction: str | None = None
    edition: str | None = None
    year: int | None = None
    publisher: str | None = None
    language: str | None = None
    pdf_pages_total: int | None = None
    source_type: SourceType | None = None


class SourceDetail(SourceRead):
    # Presigned, time-limited URL to the PDF in object storage. Populated by
    # the router, never stored — the raw pdf_object_key is not exposed.
    pdf_url: str | None = None


class SourceList(BaseModel):
    items: list[SourceRead]
    total: int
