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


class SourceDetail(SourceRead):
    # Presigned, time-limited URL to the PDF in object storage. Populated by
    # the router, never stored — the raw pdf_object_key is not exposed.
    pdf_url: str | None = None


class SourceList(BaseModel):
    items: list[SourceRead]
    total: int
