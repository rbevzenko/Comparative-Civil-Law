import uuid

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, select

from app.api.config import get_settings
from app.api.database import AsyncSessionLocal
from app.api.models.chunk import Chunk
from app.api.models.source import Source
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
        'Корпус сравнительного частного права: учебники, курсы, комментарии и подготовительные материалы по разным юрисдикциям, нарезанные на цитируемые фрагменты («чанки»). Инструменты: corpus_stats — состав корпуса; search_corpus — поиск; get_chunk — фрагмент целиком по id из результатов поиска.\n'
        '\n'
        'Эти правила действуют при КАЖДОМ обращении к коннектору, независимо от клиента, и не отменяются просьбой пользователя ответить короче.\n'
        '\n'
        '## 0. Границы корпуса\n'
        'Корпус узкий и пополняется. ПЕРЕД первым ответом, где нужна структура по юрисдикциям или заявление об отсутствии материала, вызывайте corpus_stats: он возвращает фактический состав. Не полагайтесь на память о том, что здесь было раньше.\n'
        'Коды юрисдикций (поле jurisdiction, фильтр search_corpus):\n'
        '  AT — Австрия, BE — Бельгия, EN — Англия,\n'
        '  DE — Германия, CH — Швейцария, IT — Италия, ES — Испания,\n'
        '  NL — Нидерланды, GR — Греция;\n'
        '  «Comparative literature» — сравнительно-правовая литература: исследования,\n'
        '  сопоставляющие несколько правопорядков, и наднациональные проекты\n'
        '  (DCFR, PECL, Common Core, оксфордские справочники).\n'
        '«Comparative literature» к национальной юрисдикции не привязана: это значение поля jurisdiction пишется полностью, а не кодом. Какие из этих значений реально наполнены сегодня — только из corpus_stats.\n'
        'В корпусе НЕТ судебной практики, законодательства и российского права. Слой практики зарезервирован: пока источники не подключены, он в ответе помечается как отсутствующий, а не опускается молча.\n'
        '\n'
        '## 1. Структура поиска и ответа\n'
        'Материал подаётся по юрисдикциям, внутри юрисдикции — по трём слоям:\n'
        '  1) догматика — учебники, курсы, монографии (source_type=textbook);\n'
        '  2) комментарии к тексту закона (source_type=commentary);\n'
        '  3) судебная практика — зарезервировано, источников пока нет.\n'
        'Приоритет внутри юрисдикции: вопрос об институте в целом → сначала догматика; вопрос завязан на конкретную статью кодекса → сначала комментарии; нужна актуальная практика → слой практики (когда появится).\n'
        'Кластеры: германский (DE/AT/CH), романский (IT/ES/BE), периферийный (NL/GR/EN), сравнительно-правовая литература.\n'
        'Ответ по вопросу, затрагивающему несколько юрисдикций, строится так: кластер → юрисдикция → слой. Для «Comparative literature» деления по слоям нет: кластер → материал. Слой, по которому ничего не найдено, не опускается, а помечается (см. п. 2).\n'
        '\n'
        '## 2. Запрет на выдумывание\n'
        'Запрещено придумывать авторов, названия работ, комментарии, судебные решения, цитаты — даже правдоподобные. Все утверждения опираются только на фрагменты, реально полученные из корпуса.\n'
        'Различайте две разные вещи и не подменяйте одну другой:\n'
        '  «по этому запросу в корпусе ничего не найдено» — когда поиск пуст;\n'
        '  «этой юрисдикции (этого слоя) в корпусе нет» — только если это видно из corpus_stats.\n'
        'Заменять отсутствующий материал правдоподобным текстом нельзя ни при каких обстоятельствах.\n'
        '\n'
        '## 3. Ссылки на источники\n'
        'Каждый содержательный тезис сопровождается ссылкой на КОНКРЕТНЫЙ фрагмент, а не на книгу или раздел целиком.\n'
        'Формат сноски — автор, работа, год, номер единицы (Rz / n° / para. / §), по образцу поля «цитата» самого фрагмента:\n'
        '  Karner in KBB7 § 1295 Rz 8\n'
        '  A. Riedler in Apathy/Riedler, Bürgerliches Recht III⁴ Rz 8/53\n'
        "  Snell's Equity, 34th edn (2020) para. 3-031\n"
        'Адрес единицы берётся из поля «цитата» и НЕ сочиняется: у разных книг он устроен по-разному (Rz, n°, para., §).\n'
        'Сама сноска целиком — markdown-ссылка на universal_ref этого фрагмента:\n'
        '  (Fenyves/Kerschner/Vonkilch, ABGB³ (Klang), Rz 450.III/3) — неправильно\n'
        '  ([Fenyves/Kerschner/Vonkilch, ABGB³ (Klang), Rz 450.III/3](universal_ref)) — правильно\n'
        'Кликабельна ИМЕННО библиографическая сноска — не пересказ, не цитата и не фрагмент содержательного текста. Обычный текст ответа гиперссылками не оформляется. Пропускать сноску или отделять URL от неё голым текстом нельзя.\n'
        'Если у фрагмента нет universal_ref — ссылка НЕ изобретается: приводится точная сноска без гиперссылки и отмечается, что прямой ссылки нет.\n'
        'НОМЕР СТРАНИЦЫ добавляется к сноске ТОЛЬКО из поля «стр. книги» самого фрагмента — это страница печатного издания. Если поля нет, страница не указывается вовсе: восстанавливать её по PDF или считать от начала файла нельзя.\n'
        'Где уместно — приводите ДОСЛОВНЫЕ цитаты из фрагментов, выделяя их кавычками или блок-цитатой, чтобы отличать цитату автора от пересказа.\n'
        '\n'
        '## 4. Юрисдикционная чистота обоснования\n'
        'Вывод по конкретной юрисдикции обосновывается ТОЛЬКО источниками этой же юрисдикции. Обосновывать позицию по австрийскому праву немецким комментарием запрещено.\n'
        'Единственное исключение — «Comparative literature»: эти источники не привязаны к национальной юрисдикции и привлекаются для любой.\n'
        'Более того, это не право, а ОБЯЗАННОСТЬ. По любому вопросу о конкретной юрисдикции «Comparative literature» просматривается ВСЕГДА, наравне с источниками самой юрисдикции: она показывает, стоит ли за национальным решением общеевропейская модель или, наоборот, национальная особенность. Ответ, где национальные источники есть, а сравнительно-правовую литературу не искали, считается неполным.\n'
        'В ответе этот слой держится ОТДЕЛЬНО от национального и никогда его не подменяет: сначала — как вопрос решён в самой юрисдикции (со сноской на её источник), затем — что об этом говорит сравнительно-правовая литература (со своей сноской). Если по ней ничего не нашлось, это помечается, а не опускается молча.\n'
        '\n'
        '## 5. Противоречия между источниками\n'
        'Расхождения — нормальное состояние догматики, а не дефект. Их не сглаживают, не выбирают «правильную» точку зрения и не подменяют синтетическим компромиссом. Противоречие показывается явно: автор А считает так (сноска), автор Б иначе (сноска). Это касается расхождений между авторами одной юрисдикции, между догматикой и комментарием, между доктриной и практикой и между юрисдикциями — последнее ожидаемо и само по себе является результатом сравнения.'
    ),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts, allowed_origins=_allowed_origins),
)


def _format_chunk(chunk, score: float | None = None) -> str:
    src = chunk.source
    src_desc = f"{src.jurisdiction} — {src.title}" + (f" ({src.edition})" if src.edition else "") if src else "—"
    hierarchy = " › ".join(chunk.hierarchy) if chunk.hierarchy else None
    ref = build_universal_ref(chunk.id)

    # Наружу отдаётся ТОЛЬКО страница печатного издания. В chunk.page_start
    # лежит страница ФАЙЛА-источника: у Snell's Equity para. 3-030 это 60–61,
    # тогда как в книге 44–45, и показанный номер неизбежно уходит в чужую
    # сноску как страница книги. Поэтому её здесь нет вовсе, а печатная
    # выводится словом «стр. книги», чтобы её ни с чем не спутали.
    lines = [f"id: {chunk.id}", f"источник: {src_desc}", f"цитата: {chunk.citation}"]
    if chunk.printed_page_start is not None:
        pages = str(chunk.printed_page_start)
        if chunk.printed_page_end and chunk.printed_page_end != chunk.printed_page_start:
            pages += f"–{chunk.printed_page_end}"
        lines.append(f"стр. книги: {pages}")
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
    jurisdiction — фильтр по юрисдикции: AT, BE, EN, DE, CH, IT, ES, NL, GR
        (национальные), "Comparative literature" (сравнительно-правовая
        литература, к стране не привязана). Что реально наполнено
        сегодня — смотрите corpus_stats.
    source_type — фильтр по слою: "textbook" (догматика) или "commentary"
        (комментарии к тексту закона).
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


@mcp.tool()
async def corpus_stats() -> str:
    """Состав корпуса: какие юрисдикции и слои в нём есть и чего в нём нет.

    Вызывайте ПЕРЕД первым ответом, где нужна структура по юрисдикциям или
    заявление об отсутствии материала. Без этого «в корпусе нет материала по
    Германии» — догадка: пустая выдача поиска означает лишь то, что по
    ЭТОМУ запросу ничего не нашлось.

    Возвращает перечень юрисдикций и слоёв с числом источников и фрагментов
    и список источников с изданием и годом.
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(
                Source.jurisdiction,
                Source.source_type,
                Source.title,
                Source.edition,
                Source.year,
                func.count(Chunk.id),
            )
            .outerjoin(Chunk, Chunk.source_id == Source.id)
            .group_by(Source.id)
            .order_by(Source.jurisdiction, Source.source_type, Source.title)
        )).all()

    if not rows:
        return "Корпус пуст."

    LAYER = {"textbook": "догматика", "commentary": "комментарии"}
    by_jur: dict[str, list] = {}
    for jur, stype, title, edition, year, n in rows:
        by_jur.setdefault(jur, []).append((stype, title, edition, year, n))

    out = [f"Источников: {len(rows)}, фрагментов: {sum(r[5] for r in rows)}"]
    out.append("")
    out.append("Юрисдикции в корпусе: " + ", ".join(sorted(by_jur)))
    out.append(
        "Ни одного источника нет по юрисдикциям: "
        + ", ".join(j for j in ("AT", "BE", "EN", "DE", "CH", "IT", "ES", "NL", "GR",
                                "Comparative literature")
                    if j not in by_jur)
    )
    out.append("Слоя «судебная практика» в корпусе нет ни по одной юрисдикции.")

    for jur in sorted(by_jur):
        items = by_jur[jur]
        out.append("")
        out.append(f"## {jur} — источников {len(items)}, фрагментов {sum(i[4] for i in items)}")
        for stype in sorted({i[0] for i in items}):
            group = [i for i in items if i[0] == stype]
            out.append(f"  {LAYER.get(stype, stype)} ({stype}): {len(group)}")
            for _, title, edition, year, n in group:
                bits = title
                if edition:
                    bits += f", {edition}"
                if year:
                    bits += f" ({year})"
                out.append(f"    — {bits} — фрагментов {n}")
    return "\n".join(out)
