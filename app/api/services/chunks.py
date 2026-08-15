import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models.chunk import Chunk
from app.api.models.footnote import Footnote
from app.api.schemas.chunk import ChunkCreate


async def create_chunks(db: AsyncSession, source_id: uuid.UUID, items: list[ChunkCreate]) -> list[Chunk]:
    """Shared by POST /sources/{id}/chunks and the /ui/upload/chunks form."""
    created: list[Chunk] = []
    for item in items:
        chunk = Chunk(
            source_id=source_id,
            citation=item.citation,
            point_number=item.point_number,
            text=item.text,
            hierarchy=item.hierarchy,
            page_start=item.page_start,
            page_end=item.page_end,
            embedding=item.embedding,
            concept_ids=item.concept_ids,
        )
        for fn in item.footnotes:
            chunk.footnotes.append(Footnote(number=fn.number, text=fn.text))
        db.add(chunk)
        created.append(chunk)

    await db.commit()
    for chunk in created:
        await db.refresh(chunk)
    return created
