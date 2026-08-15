import uuid

from pydantic import BaseModel, ConfigDict


class FootnoteCreate(BaseModel):
    number: int
    text: str


class FootnoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    text: str
