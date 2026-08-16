import uuid

from mcp.server.fastmcp import FastMCP

from app.api.database import AsyncSessionLocal
from app.api.schemas.search import SearchRequest
from app.api.services.chunks import get_chunk as get_chunk_record
from app.api.services.search import run_search
from app.mcp.embeddings import embed_query

mcp = FastMCP(
    name="Comparative Civil Law Corpus",
    instructions=(
        "Поиск и чтение фрагментов («чанков») корпуса сравнительного "
        "гражданского права: учебники, комментарии, статьи по разным "
        "юрисдикциям, нарезанные на цитируемые фрагменты с указанием "
        "страницы источника. search_corpus ищет; get_chunk отдаёт "
        "фрагмент целиком по id, полученному из результатов поиска."
    ),
    stateless_http=True,
    json_response=True,
)


def _format_chunk(chunk, score: float | None = None) -> str:
    src = chunk.source
    src_desc = f"{src.jurisdiction} — {src.title}" + (f" ({src.edition})" if src.edition else "") if src else "—"
    pages = str(chunk.page_start) if chunk.page_start else "—"
    if chunk.page_end and chunk.page_end != chunk.page_start:
        pages += f"–{chunk.page_end}"
    hierarchy = " › ".join(chunk.hierarchy) if chunk.hierarchy else None

    lines = [f"id: {chunk.id}", f"источник: {src_desc}", f"цитата: {chunk.citation}", f"страница: {pages}"]
    if hierarchy:
        lines.append(f"раздел: {hierarchy}")
    if score is not None:
        lines.append(f"релевантность: {score:.4f}")
    lines.append("")
    lines.append(chunk.text)
    if chunk.footnotes:
        lines.append("")
        lines.append("Сноски:")
        for fn in chunk.footnotes:
            lines.append(f"  {fn.number}. {fn.text}")
    return "\n".join(lines)


@mcp.tool()
async def search_corpus(
    query: str,
    jurisdiction: str | None = None,
    source_type: str | None = None,
    limit: int = 10,
) -> str:
    """Гибридный поиск (полнотекстовый + семантический) по корпусу.

    query — текст запроса на любом языке корпуса.
    jurisdiction — необязательный фильтр по юрисдикции (например, "AT", "FR", "DE").
    source_type — необязательный фильтр по типу источника (например, "textbook", "commentary").
    limit — сколько фрагментов вернуть (1-100, по умолчанию 10).
    """
    limit = max(1, min(limit, 100))
    embedding = await embed_query(query)
    req = SearchRequest(q=query, jurisdiction=jurisdiction, source_type=source_type, embedding=embedding, limit=limit)

    async with AsyncSessionLocal() as db:
        try:
            result = await run_search(db, req)
        except ValueError as exc:
            return str(exc)

    if not result.items:
        return "Ничего не найдено."

    blocks = [_format_chunk(item.chunk, item.score) for item in result.items]
    header = f"Найдено фрагментов: {result.total} (показаны первые {len(result.items)})"
    if embedding is None:
        header += "\n[только полнотекстовый поиск — OPENAI_API_KEY не настроен на сервере]"
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


@mcp.tool()
async def get_chunk(chunk_id: str) -> str:
    """Вернуть фрагмент целиком по его id (полученному из search_corpus)."""
    try:
        parsed_id = uuid.UUID(chunk_id)
    except ValueError:
        return f"Некорректный id: {chunk_id!r} — ожидается UUID."

    async with AsyncSessionLocal() as db:
        chunk = await get_chunk_record(db, parsed_id)

    if chunk is None:
        return f"Фрагмент с id={chunk_id} не найден."
    return _format_chunk(chunk)
