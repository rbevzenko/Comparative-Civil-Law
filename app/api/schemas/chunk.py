import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.api.models.chunk import EMBEDDING_DIM
from app.api.schemas.footnote import FootnoteCreate, FootnoteRead
from app.api.schemas.source import SourceRead
from app.api.security import build_universal_ref


class ChunkCreate(BaseModel):
    # Stable id from the external normalization pipeline. Optional, but
    # strongly recommended: when set, re-uploading the same file for this
    # source updates the matching chunks instead of duplicating them.
    external_id: str | None = None
    citation: str
    point_number: str | None = None
    text: str
    hierarchy: list[str] = Field(default_factory=list)
    # Pages of the source FILE.
    page_start: int | None = None
    page_end: int | None = None
    # Pages of the PRINTED edition — the pair a reader may cite. Optional:
    # files without a folio (Westlaw exports, most e-books) leave them unset.
    printed_page_start: int | None = None
    printed_page_end: int | None = None
    # Precomputed by the external normalization pipeline; the API does not
    # generate embeddings itself.
    embedding: list[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    footnotes: list[FootnoteCreate] = Field(default_factory=list)


class ChunkPatch(BaseModel):
    """Правка реквизитов чанка без пересчёта эмбеддинга.

    Текста здесь намеренно нет. Вектор считает внешний пайплайн, а не
    сервис; правка текста через PATCH оставила бы старый вектор при новом
    тексте — фрагмент находился бы поиском по тому, чего в нём уже нет.
    Текст меняется только полной перезаливкой через POST, вместе с
    эмбеддингом.

    «Поле не прислали» и «поле прислали пустым» — разные вещи, и различает
    их только `model_fields_set`: обнулить печатную страницу законно, и от
    «не трогай это поле» такая правка отличается лишь наличием ключа в теле
    запроса. Поэтому применяются ровно те поля, что пришли в JSON.
    """

    # extra="forbid": опечатка в имени поля должна быть ошибкой, а не тихо
    # прошедшим запросом, который ничего не изменил.
    model_config = ConfigDict(extra="forbid")

    citation: str | None = None
    point_number: str | None = None
    hierarchy: list[str] | None = None
    # Страницы файла.
    page_start: int | None = None
    page_end: int | None = None
    # Страницы печатного издания — ради них правка и заведена.
    printed_page_start: int | None = None
    printed_page_end: int | None = None

    @model_validator(mode="after")
    def _not_null_where_column_is_not_null(self) -> "ChunkPatch":
        for name in ("citation", "hierarchy"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} нельзя обнулить: колонка NOT NULL")
        return self

    def changes(self) -> dict:
        """Только присланные поля. external_id — адрес, а не значение."""
        data = self.model_dump(exclude_unset=True)
        data.pop("external_id", None)
        return data


class ChunkPatchItem(ChunkPatch):
    """Элемент пакетной правки: адресуется по external_id пайплайна.

    Внутренний uuid фрагмента пайплайну неизвестен — и не должен быть
    известен: он выдан сервисом и живёт в universal_ref. Поэтому пакет
    адресуется тем же ключом, что и загрузка.
    """

    external_id: str


class ChunkBulkPatch(BaseModel):
    chunks: list[ChunkPatchItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_external_ids(self) -> "ChunkBulkPatch":
        ids = [c.external_id for c in self.chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("external_id не уникальны внутри тела запроса")
        return self


class ChunkPatchResult(BaseModel):
    """Отчёт о пакетной правке.

    `missing` возвращается, а не превращается в 404 на весь пакет: файл
    нарезки может содержать карточки, которые в сервис не загружались, и
    ронять из-за них правку остальных незачем. Но и молчать нельзя —
    иначе несовпадение ключей выглядит как успешная правка.
    """

    updated: int
    unchanged: int
    missing: list[str] = Field(default_factory=list)


class ChunkBulkCreate(BaseModel):
    chunks: list[ChunkCreate] = Field(..., min_length=1)


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    external_id: str | None
    citation: str
    point_number: str | None
    text: str
    hierarchy: list
    page_start: int | None
    page_end: int | None
    printed_page_start: int | None
    printed_page_end: int | None
    concept_ids: list[uuid.UUID] | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def universal_ref(self) -> str | None:
        """Public, citable link to this fragment — show it next to every
        quote pulled from this chunk (see app.web.router's /source route)."""
        return build_universal_ref(self.id)


class ChunkDetail(ChunkRead):
    footnotes: list[FootnoteRead] = Field(default_factory=list)
    source: SourceRead | None = None


class ChunkList(BaseModel):
    items: list[ChunkRead]
    total: int


class ChunkWithFootnotes(ChunkRead):
    """Чанк со сносками, но БЕЗ источника.

    ChunkDetail сюда не годится: его поле `source` в списке заставило бы
    подгружать источник на каждый чанк, а он у всей страницы один и тот же.
    """

    footnotes: list[FootnoteRead] = Field(default_factory=list)


class ChunkDetailList(BaseModel):
    """Ответ списка чанков с ?with_footnotes=true — чанк отдаётся со сносками."""

    items: list[ChunkWithFootnotes]
    total: int
