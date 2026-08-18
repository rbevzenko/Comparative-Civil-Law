import uuid

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.api.config import get_settings
from app.api.database import AsyncSessionLocal
from app.api.schemas.search import SearchRequest
from app.api.security import build_universal_ref
from app.api.services.chunks import get_chunk as get_chunk_record
from app.api.services.search import run_search
from app.mcp.embeddings import embed_query

_settings = get_settings()

# The SDK's DNS-rebinding protection defaults to allowing only
# localhost/127.0.0.1 Host headers — everything arriving through the Caddy
# reverse proxy would otherwise get rejected with 421.
_allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_allowed_origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
if _settings.mcp_domain:
    _allowed_hosts += [_settings.mcp_domain, f"{_settings.mcp_domain}:*"]
    _allowed_origins.append(f"https://{_settings.mcp_domain}")

mcp = FastMCP(
    name="Comparative Civil Law Corpus",
    instructions=(
        "Поиск и чтение фрагментов («чанков») корпуса сравнительного "
        "гражданского права: учебники, комментарии, статьи по разным "
        "юрисдикциям, нарезанные на цитируемые фрагменты с указанием "
        "страницы источника. search_corpus ищет; get_chunk отдаёт "
        "фрагмент целиком по id, полученному из результатов поиска. "
        "У каждого фрагмента есть universal_ref — постоянная ссылка на "
        "страницу с этим конкретным фрагментом и его реквизитами.\n\n"
        "ОБЯЗАТЕЛЬНОЕ ПРАВИЛО: в любом ответе, где используется корпус, "
        "у КАЖДОГО опирающегося на него утверждения должна стоять "
        "библиографическая ссылка (автор, источник, § / Rz) — и эта "
        "ссылка сама должна быть markdown-гиперссылкой на universal_ref "
        "того фрагмента:\n"
        "  (Fenyves/Kerschner/Vonkilch, ABGB³ (Klang), Rz 450.III/3) — "
        "неправильно (сноска голым текстом)\n"
        "  ([Fenyves/Kerschner/Vonkilch, ABGB³ (Klang), Rz "
        "450.III/3](universal_ref)) — правильно\n"
        "Кликабельной должна быть ИМЕННО библиографическая сноска "
        "(автор + источник + номер) — а не пересказ, не цитата и не "
        "фрагмент содержательного текста ответа. Обычный текст ответа "
        "гиперссылками не оформляется вообще; единственное, что "
        "становится ссылкой — это сама сноска на источник. Пропускать "
        "сноску или отделять URL от неё голым текстом нельзя. Так же "
        "оформлены ссылки на источник в других коннекторах контура "
        "(КонсультантПлюс, «Высшие суды» и т.п.)."
    ),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts, allowed_origins=_allowed_origins),
)


def _format_chunk(chunk, score: float | None = None) -> str:
    src = chunk.source
    src_desc = f"{src.jurisdiction} — {src.title}" + (f" ({src.edition})" if src.edition else "") if src else "—"
    pages = str(chunk.page_start) if chunk.page_start else "—"
    if chunk.page_end and chunk.page_end != chunk.page_start:
        pages += f"–{chunk.page_end}"
    hierarchy = " › ".join(chunk.hierarchy) if chunk.hierarchy else None
    ref = build_universal_ref(chunk.id)

    lines = [f"id: {chunk.id}", f"источник: {src_desc}", f"цитата: {chunk.citation}", f"страница: {pages}"]
    if hierarchy:
        lines.append(f"раздел: {hierarchy}")
    if score is not None:
        lines.append(f"релевантность: {score:.4f}")
    if ref:
        lines.append(f"universal_ref: {ref}")
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

    Каждый найденный фрагмент содержит universal_ref — постоянную ссылку
    на страницу именно с этим фрагментом и его библиографическими
    реквизитами. ОБЯЗАТЕЛЬНО: у каждого утверждения в ответе, опирающегося
    на найденный фрагмент, должна быть библиографическая сноска (автор,
    источник, § / Rz), и именно эта сноска целиком оформляется как
    markdown-ссылка на universal_ref — [Автор, Источник, Rz N](universal_ref).
    Кликабельна сама сноска, а не пересказ или цитата текста фрагмента.
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
    """Вернуть фрагмент целиком по его id (полученному из search_corpus).

    Ответ содержит universal_ref — постоянную ссылку на этот фрагмент.
    ОБЯЗАТЕЛЬНО: библиографическая сноска (автор, источник, § / Rz) на
    этот фрагмент должна быть в ответе и должна сама быть markdown-
    ссылкой на universal_ref — [Автор, Источник, Rz N](universal_ref).
    Кликабельна сама сноска, а не пересказ или цитата текста фрагмента.
    """
    try:
        parsed_id = uuid.UUID(chunk_id)
    except ValueError:
        return f"Некорректный id: {chunk_id!r} — ожидается UUID."

    async with AsyncSessionLocal() as db:
        chunk = await get_chunk_record(db, parsed_id)

    if chunk is None:
        return f"Фрагмент с id={chunk_id} не найден."
    return _format_chunk(chunk)
