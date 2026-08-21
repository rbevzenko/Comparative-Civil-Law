import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.models.chunk import Chunk
from app.api.models.footnote import Footnote
from app.api.schemas.chunk import ChunkCreate, ChunkPatchItem


async def get_chunk(db: AsyncSession, chunk_id: uuid.UUID) -> Chunk | None:
    """Shared by GET /chunks/{id} and the MCP get_chunk tool."""
    stmt = (
        select(Chunk)
        .where(Chunk.id == chunk_id)
        .options(selectinload(Chunk.footnotes), selectinload(Chunk.source))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_chunks(db: AsyncSession, source_id: uuid.UUID, items: list[ChunkCreate]) -> list[Chunk]:
    """Shared by POST /sources/{id}/chunks and the /ui/upload/chunks form.

    Chunks carrying an `external_id` are upserted: re-uploading the same
    normalization output for this source (the same file twice, or a
    corrected re-run) updates the existing rows instead of duplicating
    them. Chunks without an external_id are always inserted as new rows —
    there is nothing to match them against.
    """
    external_ids = [item.external_id for item in items if item.external_id is not None]
    existing_by_external_id: dict[str, Chunk] = {}
    if external_ids:
        stmt = (
            select(Chunk)
            .where(Chunk.source_id == source_id, Chunk.external_id.in_(external_ids))
            .options(selectinload(Chunk.footnotes))
        )
        for chunk in (await db.execute(stmt)).scalars():
            existing_by_external_id[chunk.external_id] = chunk

    result: list[Chunk] = []
    for item in items:
        existing = existing_by_external_id.get(item.external_id) if item.external_id else None
        if existing is not None:
            existing.citation = item.citation
            existing.point_number = item.point_number
            existing.text = item.text
            existing.hierarchy = item.hierarchy
            existing.page_start = item.page_start
            existing.page_end = item.page_end
            existing.printed_page_start = item.printed_page_start
            existing.printed_page_end = item.printed_page_end
            existing.embedding = item.embedding
            existing.concept_ids = item.concept_ids
            existing.footnotes.clear()
            for fn in item.footnotes:
                existing.footnotes.append(Footnote(number=fn.number, text=fn.text))
            result.append(existing)
        else:
            chunk = Chunk(
                source_id=source_id,
                external_id=item.external_id,
                citation=item.citation,
                point_number=item.point_number,
                text=item.text,
                hierarchy=item.hierarchy,
                page_start=item.page_start,
                page_end=item.page_end,
                printed_page_start=item.printed_page_start,
                printed_page_end=item.printed_page_end,
                embedding=item.embedding,
                concept_ids=item.concept_ids,
            )
            for fn in item.footnotes:
                chunk.footnotes.append(Footnote(number=fn.number, text=fn.text))
            db.add(chunk)
            result.append(chunk)

    await db.commit()
    for chunk in result:
        await db.refresh(chunk)
    return result


async def patch_chunks_by_external_id(
    db: AsyncSession, source_id: uuid.UUID, items: list[ChunkPatchItem]
) -> tuple[int, int, list[str]]:
    """Правка реквизитов пачки чанков одного источника без эмбеддингов.

    Заведено ради дозаливки печатных страниц: карточки грузились в сервис
    до появления колонок `printed_page_*`, и без правки на месте пришлось
    бы перезаливать весь корпус целиком — то есть заново считать сто
    шестнадцать тысяч векторов ради двух целых чисел на карточку.

    Возвращает (изменено, совпало-но-нечего-менять, ненайденные ключи).
    Второе число отделено от первого не для красоты: при дозаливке оно
    показывает, сколько карточек уже несут правильные значения, и по нему
    видно, что повторный прогон ничего не портит.
    """
    by_external_id: dict[str, Chunk] = {}
    external_ids = [item.external_id for item in items]
    stmt = select(Chunk).where(Chunk.source_id == source_id, Chunk.external_id.in_(external_ids))
    for chunk in (await db.execute(stmt)).scalars():
        by_external_id[chunk.external_id] = chunk

    updated = unchanged = 0
    missing: list[str] = []
    for item in items:
        chunk = by_external_id.get(item.external_id)
        if chunk is None:
            missing.append(item.external_id)
            continue
        if apply_patch(chunk, item.changes()):
            updated += 1
        else:
            unchanged += 1

    if updated:
        await db.commit()
    return updated, unchanged, missing


def apply_patch(chunk: Chunk, changes: dict) -> bool:
    """Кладёт присланные поля в чанк. True, если что-то реально поменялось.

    Сравнение со старым значением нужно, чтобы не будить `onupdate` у
    `updated_at`: пробег по всему корпусу, где половина карточек уже верна,
    не должен выглядеть так, будто их правили.
    """
    touched = False
    for name, value in changes.items():
        if getattr(chunk, name) != value:
            setattr(chunk, name, value)
            touched = True
    return touched


async def patch_chunk(db: AsyncSession, chunk_id: uuid.UUID, changes: dict) -> Chunk | None:
    """Точечная правка одного чанка по внутреннему uuid."""
    chunk = await db.get(Chunk, chunk_id)
    if chunk is None:
        return None
    if apply_patch(chunk, changes):
        await db.commit()
    return await get_chunk(db, chunk_id)
