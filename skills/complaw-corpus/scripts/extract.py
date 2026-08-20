#!/usr/bin/env python3
"""
Сборка карточек из модели страницы по профилю.

Usage:
    python extract.py --book books/<book-id> --profile profiles/x.yaml --meta meta.json

Вход — work/pages.jsonl, который сделала одна из веток (pages_digital.py или
ocr.py). Дальше обе ветки идут одинаково, потому что разница между сканом и
цифровым файлом уже отработана и в модели страницы её нет.

Выход:
    work/book.txt        нормализованный текст книги, в него смотрят офсеты
    work/pagemap.json    офсеты → страница файла и типографская страница
    work/units.json      найденные единицы с уликами, до сборки карточек
    output/cards.jsonl   карточки (внутреннее каноническое представление)
    report/extract_issues.json  всё, что не удалось решить механически

Ни одного решения не принимает модель. Границы, адреса, сноски, нормы —
из профиля и из вёрстки. Чего нельзя получить механически, попадает в
issues, а не додумывается (§3.2).
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipelib as P


# ---------- 1. строки книги и карта страниц ----------

def load_pages(book):
    path = os.path.join(book, "work", "pages.jsonl")
    if not os.path.exists(path):
        sys.exit(f"Нет {path}. Сначала ветка A (pages_digital.py) или B (ocr.py).")
    meta_path = os.path.join(book, "work", "pages_meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    return P.read_jsonl(path), meta


def pull_margin_tokens(pages, prof):
    """Снимает маргинальные номера со строк тела и возвращает их отдельно.

    Делать это надо до сборки book.txt: номер на поле визуально стоит на
    одной строке с телом и иначе попадёт внутрь текста карточки.

    Поле считается ПО КАЖДОЙ СТРАНИЦЕ отдельно (`margin.scope: page`).
    На книжном скане полоса набора гуляет от страницы к странице на десятки
    пунктов: общий на книгу коридор либо режет часть номеров, либо залезает
    в текст и ловит числа в конце строк. Границей служат нечисловые слова
    длинных строк — иначе сам маргинальный номер растягивает полосу на себя.
    """
    cfg = (prof.get("margin") or {})
    parity = cfg.get("parity", "pdf")
    scope = cfg.get("scope", "page")
    pad = float(cfg.get("pad", 2.0))

    known = [(pg["printed_page"], pg["pdf_page"]) for pg in pages if pg.get("printed_page")]
    offset = statistics.median([p - f for p, f in known]) if known else 0

    def parity_page(pg):
        if parity != "printed":
            return pg["pdf_page"]
        return int(pg.get("printed_page") or (pg["pdf_page"] + offset))

    book_cols = None
    if scope != "page":
        book_cols = P.margin_columns(pages, side=cfg.get("side_hint"), parity=parity)

    manual = cfg.get("x_range")
    tokens = defaultdict(list)
    stats = {"pages_with_body": 0, "pages_without_body": 0}

    for pg in pages:
        pno = parity_page(pg)
        side = P.margin_side(pno, cfg) if cfg.get("side") else "both"

        if manual:
            lo, hi = float(manual[0]), float(manual[1])
            in_margin = lambda w: lo <= (w["x0"] + w["x1"]) / 2 <= hi
        elif book_cols is not None:
            cols = [c for c in book_cols["odd" if pno % 2 == 1 else "even"]
                    if side in ("both", c["side"])]
            in_margin = lambda w: any(c["x0"] <= (w["x0"] + w["x1"]) / 2 <= c["x1"] for c in cols)
        else:
            edge = _page_body_edges(pg)
            if edge is None:
                stats["pages_without_body"] += 1
                continue
            stats["pages_with_body"] += 1
            body_l, body_r = edge
            def in_margin(w, body_l=body_l, body_r=body_r, side=side, first=None, last=None):
                # Маргиналия стоит ЗА полосой набора и всегда с краю строки:
                # первым словом у левого поля, последним у правого. Число в
                # середине строки — ссылка в тексте или хвост сноски, и
                # маргиналией не является, как бы близко к краю оно ни было.
                if side in ("left", "both") and w is first and w["x1"] <= body_l - pad:
                    return True
                if side in ("right", "both") and w is last and w["x0"] >= body_r + pad:
                    return True
                return False

        for li, ln in enumerate(pg["lines"]):
            keep, taken = [], []
            words = sorted(ln["words"], key=lambda w: w["x0"])
            first, last = (words[0], words[-1]) if words else (None, None)
            for w in ln["words"]:
                s = w["text"].strip().strip(".)")
                try:
                    hit = in_margin(w, first=first, last=last)
                except TypeError:                   # ручной x_range и книжные коридоры
                    hit = in_margin(w)
                is_margin = bool(re.fullmatch(r"\d{1,4}", s)) and hit
                (taken if is_margin else keep).append(w)
            if taken:
                pg["lines"][li] = dict(ln, **{
                    "text": " ".join(w["text"] for w in keep).strip(),
                    "words": keep,
                    "x0": min((w["x0"] for w in keep), default=ln["x0"]),
                    "x1": max((w["x1"] for w in keep), default=ln["x1"]),
                })
                for w in taken:
                    tokens[(pg["pdf_page"], li)].append(w)
    return tokens


def _page_body_edges(pg, min_len=40, min_lines=4):
    """Левая и правая границы полосы набора на странице.

    Считаются по длинным строкам и только по нечисловым словам: число в
    начале строки — это маргиналия, число в конце — ссылка внутри текста или
    хвост сноски, и ни то ни другое границей полосы не является.
    """
    lefts, rights = [], []
    for ln in pg["lines"]:
        words = [w for w in ln.get("words", [])
                 if not re.fullmatch(r"\d{1,4}", w["text"].strip())]
        if len(ln["text"]) > min_len and words:
            lefts.append(min(w["x0"] for w in words))
            rights.append(max(w["x1"] for w in words))
    if len(lefts) < min_lines:
        return None
    return statistics.median(lefts), statistics.median(rights)


def build_text(pages):
    """book.txt плюс индекс строк с координатами и офсетами.

    book.txt хранится рядом с карточками не как промежуточный файл:
    перенарезка при изменении правил — это перезапуск по нему, а не
    повторный разбор PDF или OCR.
    """
    parts, index, pagemap, off = [], [], [], 0
    for pg in pages:
        page_start = off
        for li, ln in enumerate(pg["lines"]):
            s = ln["text"]
            if not s:
                continue
            index.append({
                "i": len(index), "pdf_page": pg["pdf_page"], "printed_page": pg.get("printed_page"),
                "line_no": li, "start": off, "end": off + len(s), "text": s,
                "x0": ln["x0"], "x1": ln["x1"], "top": ln["top"], "bottom": ln["bottom"],
                "size": ln.get("size"),
                "width": pg["width"], "height": pg["height"],
            })
            parts.append(s)
            off += len(s) + 1
        if off > page_start:
            pagemap.append({"pdf_page": pg["pdf_page"], "printed_page": pg.get("printed_page"),
                            "start": page_start, "end": off - 1})
    return "\n".join(parts), index, pagemap


# ---------- 2. разделы для составного адреса ----------

def section_map(index, prof, outline_sections):
    """Номер раздела (§ NNN) для каждой строки.

    У немецких комментариев номер параграфа кодекса — часть адреса, а не
    иерархии: «§ 812 Rn. 45» без «§ 812» бессмысленно, и без него же
    id столкнётся с чужим при перезапуске нумерации (§20, четвёртый пункт).
    """
    cfg = prof.get("address", {}).get("section", {}) or {}
    mode = cfg.get("mode")
    if not mode or mode == "none":
        return [None] * len(index), []

    cur, out, found = None, [], []
    rx = re.compile(cfg["pattern"]) if cfg.get("pattern") else None
    by_page = {}
    if mode == "outline":
        by_page = {e["page"]: e["section"] for e in outline_sections}

    for ln in index:
        if mode == "outline":
            if ln["pdf_page"] in by_page:
                cur = by_page[ln["pdf_page"]]
        elif rx is not None:
            m = rx.match(ln["text"]) if cfg.get("anchor", "start") == "start" else rx.search(ln["text"])
            if m:
                cur = m.group(1)
                found.append({"section": cur, "line": ln["i"], "pdf_page": ln["pdf_page"]})
        out.append(cur)
    return out, found


# ---------- 3. поиск единиц ----------

def find_units(index, tokens, prof, sections, method):
    """Единицы всех семейств профиля, отсортированные по месту в книге.

    Семейств может быть несколько: у учебника с задачами номера Rz и номера
    Fall — разные ряды, и мерить их непрерывность надо порознь.
    """
    hits = []
    for fam in prof["units"]:
        mode = fam.get("mode", "flow")
        if mode == "flow":
            hits += _flow(index, fam)
        elif mode == "margin":
            hits += _margin(index, tokens, fam)
        elif mode == "heading":
            hits += _heading(index, fam)
        elif mode == "page":
            hits += _page(index, fam)
        else:
            sys.exit(f"Неизвестный режим единицы: {mode}")

    hits.sort(key=lambda h: (h["line"], h["order"]))
    return validate_numbers(hits, sections, method)


def _flow(index, fam):
    """Единица — номер в начале строки.

    Кегль строки (`size_min` / `size_max` в семействе) отсекает то, что
    выглядит номером единицы, но ею не является. У McKendrick, Contract Law
    номера разделов набраны кеглем 12 и 11, а тем же «N.N» открываются
    вопросы для самопроверки в конце главы, набранные кеглем 9: без порога
    они становятся единицами и дублируют настоящие разделы.
    """
    rx = re.compile(fam["pattern"])
    lo, hi = fam.get("size_min"), fam.get("size_max")
    out = []
    for ln in index:
        if lo is not None and (ln.get("size") is None or ln["size"] < lo):
            continue
        if hi is not None and (ln.get("size") is None or ln["size"] > hi):
            continue
        m = rx.match(ln["text"])
        if m:
            out.append({"family": fam, "number_raw": m.group(1), "line": ln["i"],
                        "order": 0, "mode": "flow", "evidence": {"line_text": ln["text"][:80]},
                        "strip": m.end()})
    return out


def _margin(index, tokens, fam):
    """Маргинальный номер → строка тела, стоящая на той же высоте."""
    by_page = defaultdict(list)
    for ln in index:
        by_page[ln["pdf_page"]].append(ln)
    out = []
    for (page, line_no), words in sorted(tokens.items()):
        lines = by_page.get(page) or []
        if not lines:
            continue
        for k, w in enumerate(sorted(words, key=lambda w: w["top"])):
            target = min(lines, key=lambda ln: (abs(ln["top"] - w["top"]), ln["i"]))
            out.append({"family": fam, "number_raw": w["text"].strip().strip(".)"),
                        "line": target["i"], "order": k, "mode": "margin",
                        "evidence": {"margin_x": round(w["x0"], 1), "margin_top": round(w["top"], 1),
                                     "dy": round(abs(target["top"] - w["top"]), 1),
                                     "line_text": target["text"][:80]},
                        "strip": 0})
    return out


def _heading(index, fam):
    """Запасной режим: единица — подраздел по заголовку источника.

    Более дробную единицу не изобретаем, даже если текст это позволяет (§7).

    Кегль строки (`size_min` / `size_max`) отсекает то же, что и во `_flow`.
    У Duddington, Law Express: Land Law заголовок отличается от тела ТОЛЬКО
    кеглем (18 и 16 против 10) и никакого различимого паттерна не имеет:
    это обычная фраза со строчной буквы.
    """
    rx = re.compile(fam["pattern"])
    lo, hi = fam.get("size_min"), fam.get("size_max")
    out, n = [], 0
    for ln in index:
        if lo is not None and (ln.get("size") is None or ln["size"] < lo):
            continue
        if hi is not None and (ln.get("size") is None or ln["size"] > hi):
            continue
        m = rx.match(ln["text"])
        if not m:
            continue
        n += 1
        num = m.group(1) if m.groups() else str(n)
        out.append({"family": fam, "number_raw": num, "line": ln["i"], "order": 0,
                    "mode": "heading", "evidence": {"heading": ln["text"][:120]}, "strip": 0})
    return out


def _page(index, fam):
    """Единица — типографская страница.

    Для книги, у которой нет НИ нумерации абзацев, НИ достаточного числа
    заголовков. У Lawson & Rudden, The Law of Property (Clarendon Law
    Series) заголовок стоит раз в четыре полосы: по ним выходит 39 карточек
    на 198 полос, из них девять длиннее 18 000 знаков — эмбеддер таких не
    видит целиком. При этом книга и цитируется страницей: «Lawson & Rudden,
    The Law of Property, 3rd edn, p. 47».

    Резать по границе полосы — не выдумка структуры, а ровно та единица,
    которой книга пользуется сама.
    """
    out, seen = [], set()
    for ln in index:
        # Ключ составной: у скана разворота (см. scripts/pages_spread.py) на
        # одном листе две полосы книги, у обеих один pdf_page и разные
        # колонцифры.
        key = (ln["pdf_page"], ln.get("printed_page"))
        if key in seen:
            continue
        seen.add(key)
        num = ln.get("printed_page")
        out.append({"family": fam, "number_raw": str(num if num is not None else ln["pdf_page"]),
                    "line": ln["i"], "order": 0, "mode": "page",
                    "evidence": {"pdf_page": ln["pdf_page"], "printed_page": num},
                    "strip": 0})
    return out


def validate_numbers(hits, sections, method):
    """Ожидаемый следующий номер по каждому ряду + починка подмен OCR.

    Ряд — это (семейство, раздел): в комментариях нумерация перезапускается
    внутри каждого параграфа, и сквозной непрерывности там не бывает.
    """
    expected, issues = {}, []
    for h in hits:
        # Семейство может стоять вне разделов: задачи и примеры в конце книги
        # нумеруются сквозняком, и приписывать им последний параграф нельзя.
        use_sec = h["family"].get("use_section", True)
        sec = sections[h["line"]] if (sections and use_sec) else None
        key = (h["family"]["id_prefix"], sec)
        exp = expected.get(key)
        num, audit = P.repair_number(h["number_raw"], exp)
        if audit:
            audit.update({"line": h["line"], "family": h["family"]["id_prefix"], "section": sec,
                          "method": method})
            issues.append(audit)
        if num is None:
            h["dropped"] = "нечитаемый номер"
            continue
        h["number"] = num
        h["section"] = sec
        h["row_key"] = key
        expected[key] = num + 1

    hits = [h for h in hits if "number" in h]
    issues += repair_by_neighbours(hits)
    return hits, issues


def repair_by_neighbours(hits):
    """Починка номера, который сам по себе читается, но рвёт последовательность.

    Опечатка в цифре не обязана делать номер нечитаемым: «975» превращается в
    «915», и ряд получает разрыв в шестьдесят номеров на ровном месте. Правка
    делается только тогда, когда СЛЕДУЮЩИЙ номер подтверждает ожидание, а
    отличие от ожидаемого — ровно в одном знаке той же длины. Иначе номер
    остаётся как есть: молча подгонять адрес под красивую последовательность
    нельзя, это и есть выдуманная ссылка.
    """
    def hamming1(a, b):
        return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1

    by_row = defaultdict(list)
    for h in hits:
        by_row[h.get("row_key")].append(h)

    issues = []
    for row in by_row.values():
        for i in range(1, len(row) - 1):
            prev, cur, nxt = row[i - 1]["number"], row[i]["number"], row[i + 1]["number"]
            exp = prev + 1
            if cur == exp or nxt != exp + 1:
                continue
            if not hamming1(str(cur), str(exp)):
                continue
            issues.append({"raw": str(cur), "action": "repaired_by_neighbours", "to": exp,
                           "expected": exp, "line": row[i]["line"],
                           "evidence": f"предыдущий {prev}, следующий {nxt}"})
            row[i]["number"] = exp
            row[i]["number_raw"] = str(cur)
    return issues


# ---------- 4. границы, поглощение, иерархия ----------

def assemble(hits, index, text):
    """Начало следующей единицы — конец предыдущей.

    Если две единицы сели на одну строку, границы между ними в источнике
    нет. Выдумывать её нельзя: остаётся одна карточка, вторая уходит в
    contains_also и адресуется в неё же (§12).
    """
    units, absorbed = [], defaultdict(list)
    for h in hits:
        if units and h["line"] == units[-1]["line"]:
            absorbed[len(units) - 1].append(h)
            continue
        units.append(h)

    for k, u in enumerate(units):
        start_line = index[u["line"]]
        end_line = index[units[k + 1]["line"] - 1] if k + 1 < len(units) else index[-1]
        if k + 1 < len(units) and units[k + 1]["line"] <= u["line"]:
            end_line = start_line
        u["char_start"] = start_line["start"] + u.get("strip", 0)
        u["char_end"] = end_line["end"]
        u["line_end"] = end_line["i"]
        u["text"] = text[u["char_start"]:u["char_end"]].strip()
        u["absorbed"] = absorbed.get(k, [])
    return units


NORM_RX = re.compile(r"[^0-9a-zà-ÿäöüß]+", re.IGNORECASE)


def _norm(s):
    return NORM_RX.sub(" ", (s or "").lower()).strip()


def load_printed_toc(book):
    """Печатное оглавление, разобранное toc_parse.py."""
    path = os.path.join(book, "work", "toc.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def anchor_toc(entries, index, window=1, min_ratio=0.72):
    """Привязка узлов оглавления к строкам тела.

    Оглавление знает только страницу начала раздела, а на странице разделов
    бывает несколько. Поэтому заголовок ищется в самом тексте — на своей
    странице и соседних, — и узел садится на найденную строку. Не нашлось —
    узел остаётся с точностью до страницы, и это видно в отчёте.
    """
    import difflib
    by_printed = defaultdict(list)
    known = [(ln["printed_page"], ln["pdf_page"]) for ln in index if ln["printed_page"]]
    offset = statistics.median([p - f for p, f in known]) if known else 0
    for ln in index:
        p = ln["printed_page"] or (ln["pdf_page"] + offset)
        by_printed[int(p)].append(ln)

    anchored = 0
    for e in entries:
        target, best = None, 0.0
        want = _norm(e.get("title") or e.get("raw"))
        if not want:
            continue
        head = want[:40]
        for p in range(e["printed_page"] - window, e["printed_page"] + window + 1):
            for ln in by_printed.get(p, []):
                got = _norm(ln["text"])
                if not got:
                    continue
                if got.startswith(head[:20]) or head[:20] in got[:60]:
                    r = 1.0
                else:
                    r = difflib.SequenceMatcher(None, head, got[:len(head) + 10]).ratio()
                if r > best:
                    best, target = r, ln
        if target is not None and best >= min_ratio:
            e["line"] = target["i"]
            e["anchor_ratio"] = round(best, 2)
            anchored += 1
        else:
            first = by_printed.get(e["printed_page"])
            if first:
                e["line"] = first[0]["i"]
            elif known and e["printed_page"] < min(p for p, _ in known):
                # Узел начался раньше обработанного куска книги: он всё равно
                # накрывает его целиком, иначе у карточек пропадут верхние
                # уровни — часть, глава, раздел.
                e["line"] = -1
            else:
                e["line"] = None            # узел лежит за пределами куска
            e["anchor_ratio"] = round(best, 2)
            e["anchored_by_page_only"] = True
    return anchored


def hierarchy_from_toc(entries, line_i):
    """Цепочка заголовков над строкой: по узлу на каждый уровень."""
    chain = {}
    for e in entries:
        if e.get("line") is None or e["line"] > line_i:
            continue
        chain[e["depth"]] = e
        for d in [d for d in chain if d > e["depth"]]:
            del chain[d]
    # В иерархию идёт заголовок вместе с его маркером: «G. Gesetzesauslegung»
    # проверяется по книге, а «Gesetzesauslegung» — уже нет.
    return [chain[d].get("raw") or chain[d].get("title") for d in sorted(chain)]


def read_outline(pdf_path, section_pattern=None, page_range=None):
    if not pdf_path or not os.path.exists(pdf_path):
        return [], []
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        outline = reader.outline
    except Exception:
        return [], []
    flat = []

    def walk(node, depth=0):
        for item in node:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                try:
                    pg = reader.get_destination_page_number(item) + 1
                except Exception:
                    continue
                flat.append({"title": str(getattr(item, "title", "")).strip(),
                             "page": pg, "depth": depth})

    try:
        walk(outline or [])
    except Exception:
        return [], []
    if page_range:
        # Обложка, реклама издательства и регистры тоже сидят в зашитом
        # оглавлении. Без отсечения они всплывают в иерархии карточек как
        # «Bürgerliches Recht → Grundriss → Band II».
        lo, hi = page_range
        flat = [e for e in flat if lo <= e["page"] <= hi]
    flat.sort(key=lambda e: (e["page"], e["depth"]))
    sections = []
    if section_pattern:
        rx = re.compile(section_pattern)
        for e in flat:
            m = rx.search(e["title"] or "")
            if m:
                sections.append({"section": m.group(1), "page": e["page"]})
    return flat, sections


def hierarchy_for(outline, page):
    """Оглавление — улика, а не источник власти: кривые узлы схлопываем."""
    if not outline or page is None:
        return []
    branch = {}
    for e in outline:
        if e["page"] <= page:
            branch[e["depth"]] = e["title"]
            for d in [d for d in branch if d > e["depth"]]:
                del branch[d]
        else:
            break
    out = []
    for d in sorted(branch):
        if not out or out[-1] != branch[d]:
            out.append(branch[d])
    return out


# ---------- 5. сноски ----------

def attach_notes(units, pages, pagemap):
    """Сноски страницы отдаются занимающей её единице.

    Собраны они были постранично ещё в ветке: нумерация сбрасывается на
    каждой странице, а единица идёт через разворот. Если на странице
    несколько единиц, сноска уходит той, в чьём тексте найден её номер,
    иначе — занимающей больше места.
    """
    by_unit = defaultdict(list)
    spans = [(u["char_start"], u["char_end"], k) for k, u in enumerate(units)]
    pm = {e["pdf_page"]: e for e in pagemap}

    for pg in pages:
        notes = pg.get("notes") or []
        if not notes:
            continue
        e = pm.get(pg["pdf_page"])
        if not e:
            continue
        here = [(s, en, k) for s, en, k in spans if s <= e["end"] and en >= e["start"]]
        if not here:
            continue
        for note in notes:
            target = None
            if len(here) > 1 and note.get("number") is not None:
                marker = re.compile(r"(?<!\d)%d(?!\d)" % note["number"])
                for s, en, k in here:
                    if marker.search(units[k]["text"]):
                        target = k
                        break
            if target is None:
                target = max(here, key=lambda t: min(t[1], e["end"]) - max(t[0], e["start"]))[2]
            by_unit[target].append(note)
    return by_unit


# ---------- 6. адрес, цитата, id ----------

def address_of(u, prof, printed_page):
    fam = u["family"]
    tpl = fam.get("address_template") or prof.get("address", {}).get("template")
    if not tpl or not u.get("section"):
        tpl = fam.get("address_template") or (
            "{section_prefix}{unit_type} {number}" if u.get("section") else "{unit_type} {number}")
    return re.sub(r"\s+", " ", tpl.format(
        unit_type=fam["type"], number=u["number"], section=u.get("section") or "",
        section_prefix=f"§ {u['section']} " if u.get("section") else "",
        page=printed_page or "", hierarchy="/".join(u.get("hierarchy") or []),
    )).strip(" ,")


def citation_of(u, prof, meta, address):
    tpl = prof.get("citation", {}).get("template",
                                       "{authors}, {title}, {edition}, {publisher}, {year}, {address}")
    # Поля meta доступны в шаблоне как есть: у книги может быть собственный
    # Zitiervorschlag на обороте титула, и он важнее нашей реконструкции.
    fields = {k: v for k, v in meta.items() if not isinstance(v, (list, dict))}
    fields.update(
        authors=", ".join(meta.get("authors", [])), title=meta.get("title", ""),
        edition=meta.get("edition", ""), publisher=meta.get("publisher", ""),
        year=meta.get("year", ""), address=address, unit_type=u["family"]["type"],
        unit=u["number"], number=u["number"], section=u.get("section") or "",
    )
    try:
        s = tpl.format(**fields)
    except KeyError as e:
        sys.exit(f"В шаблоне цитирования есть поле {e}, которого нет в meta.json")
    return re.sub(r"\s+", " ", s).replace(" ,", ",").strip(" ,")


def ids_of(u, book_id):
    """Детерминированные id: одинаковый источник даёт одинаковый id всегда.

    external_id несёт и книгу, и семейство, и раздел — иначе перезапуск
    нумерации внутри параграфов даёт коллизии.
    """
    fam, sec, num = u["family"]["id_prefix"], u.get("section"), u["number"]
    ext = f"{book_id}:{fam}:{sec}/{num}" if sec else f"{book_id}:{fam}:{num}"
    legacy = f"{book_id}-{fam}{sec}-{num}" if sec else f"{book_id}-{fam}{num}"
    return ext, legacy


def bbox_of(index, u):
    """Нормализованные рамки по страницам, чтобы карточку можно было показать."""
    boxes = {}
    for ln in index[u["line"]:u["line_end"] + 1]:
        b = boxes.setdefault(ln["pdf_page"], [1.0, 1.0, 0.0, 0.0])
        b[0] = min(b[0], ln["x0"] / ln["width"])
        b[1] = min(b[1], ln["top"] / ln["height"])
        b[2] = max(b[2], ln["x1"] / ln["width"])
        b[3] = max(b[3], ln["bottom"] / ln["height"])
    return [{"pdf_page": p, "bbox": [round(v, 4) for v in b]} for p, b in sorted(boxes.items())]


# ---------- сборка ----------

def build(book, prof, meta, source_pdf):
    pages, pmeta = load_pages(book)
    method = pmeta.get("method", "unknown")
    tokens = pull_margin_tokens(pages, prof) if any(
        f.get("mode") == "margin" for f in prof["units"]) else {}

    text, index, pagemap = build_text(pages)
    if not index:
        sys.exit("В модели страницы нет ни одной строки тела. Проверьте профиль и ветку.")

    sec_cfg = prof.get("address", {}).get("section", {}) or {}
    outline, outline_sections = read_outline(
        source_pdf, sec_cfg.get("outline_pattern"),
        (prof.get("hierarchy") or {}).get("outline_pages"))
    toc = load_printed_toc(book)
    toc_entries = sorted(toc["entries"], key=lambda e: (e["printed_page"], e["depth"])) if toc else []
    toc_anchored = anchor_toc(toc_entries, index) if toc_entries else 0
    sections, sec_found = section_map(index, prof, outline_sections)

    hits, number_issues = find_units(index, tokens, prof, sections, method)
    if not hits:
        sys.exit("Ни одна единица не найдена. Профиль не подходит книге — вернуться к паспорту "
                 "(diagnose.py), а не подкручивать паттерн наугад.")
    units = assemble(hits, index, text)
    notes_by_unit = attach_notes(units, pages, pagemap)

    stat_rx = P.compile_patterns(prof.get("statutory", {}).get("patterns"))
    xref_rx = P.compile_patterns(prof.get("cross_refs", {}).get("patterns"))
    book_id = meta.get("book_id") or P.slugify(f"{meta.get('title', 'book')}-{meta.get('edition', '')}")
    digest = pmeta.get("source_sha256") or (P.sha256_file(source_pdf) if source_pdf else None)

    cards = []
    for k, u in enumerate(units):
        start_line, end_line = index[u["line"]], index[u["line_end"]]
        u["hierarchy"] = (hierarchy_from_toc(toc_entries, u["line"]) if toc_entries
                          else hierarchy_for(outline, start_line["pdf_page"]))
        address = address_of(u, prof, start_line["printed_page"])
        ext_id, legacy_id = ids_of(u, book_id)
        contains = []
        for a in u["absorbed"]:
            a_ext, _ = ids_of(dict(a, section=u.get("section")), book_id)
            contains.append({"external_id": a_ext, "unit_type": a["family"]["type"],
                             "number": a["number"], "reason": "нет границы в источнике"})
        cards.append({
            # --- идентичность ---
            "external_id": ext_id,
            "id": legacy_id,
            "book_id": book_id,
            # --- цитирование ---
            "unit": u["family"]["type"],
            "unit_type": u["family"]["type"],
            "unit_number": str(u["number"]),
            "number": u["number"],
            "section": u.get("section"),
            "address": address,
            "citation": citation_of(u, prof, meta, address),
            # --- содержание ---
            "text": u["text"],
            "hierarchy": u["hierarchy"],
            "footnotes": sorted(notes_by_unit.get(k, []), key=lambda n: (n["page"], n["number"] if n["number"] is not None else 10**6)),
            "statutory_refs": P.find_all(stat_rx, u["text"]),
            "cross_refs": P.find_all(xref_rx, u["text"]),
            "contains_also": contains,
            "institute": None,
            "concept_ids": [],
            # --- происхождение ---
            "source": {k2: meta.get(k2) for k2 in ("authors", "title", "edition", "year", "publisher")},
            "jurisdiction": meta.get("jurisdiction") or prof.get("jurisdiction"),
            "language": meta.get("language") or prof.get("language"),
            "page_start": start_line["pdf_page"],
            "page_end": end_line["pdf_page"],
            "printed_page_start": start_line["printed_page"],
            "printed_page_end": end_line["printed_page"],
            "char_start": u["char_start"],
            "char_end": u["char_end"],
            "bbox": bbox_of(index, u),
            "source_file": os.path.basename(source_pdf) if source_pdf else None,
            "source_sha256": digest,
            "method": method,
            "detection_mode": u["mode"],
            "detection_evidence": u["evidence"],
            "profile": prof.get("id"),
            "chunk_version": P.SCHEMA_VERSION,
        })

    d = P.book_dirs(book)
    P.atomic_write(os.path.join(d["work"], "book.txt"), text)
    P.write_json(os.path.join(d["work"], "pagemap.json"), pagemap)
    P.write_json(os.path.join(d["work"], "units.json"),
                 [{k2: v for k2, v in u.items() if k2 not in ("family", "text", "absorbed")}
                  | {"family": u["family"]["id_prefix"], "absorbed": len(u["absorbed"])} for u in units])
    P.write_jsonl(os.path.join(d["output"], "cards.jsonl"), cards)

    issues = {
        "number_issues": number_issues,
        "absorbed_units": sum(len(u["absorbed"]) for u in units),
        "sections_found": len(sec_found) or len(outline_sections),
        "toc_entries": len(toc_entries),
        "toc_anchored_to_line": toc_anchored,
        "toc_page_only": sum(1 for e in toc_entries if e.get("anchored_by_page_only")),
        "pages_without_lines": [pg["pdf_page"] for pg in pages if not pg["lines"]],
        "profile": prof.get("id"), "method": method,
    }
    P.write_json(os.path.join(d["report"], "extract_issues.json"), issues)

    by_family = Counter(c["unit_type"] for c in cards)
    print(f"Карточек: {len(cards)} " + ", ".join(f"{k}: {v}" for k, v in by_family.items()))
    print(f"Страниц: {len(pages)}, текст книги: {len(text)} символов")
    if issues["number_issues"]:
        print(f"Спорных номеров: {len(issues['number_issues'])} — см. report/extract_issues.json")
    if issues["absorbed_units"]:
        print(f"Поглощённых единиц (contains_also): {issues['absorbed_units']}")
    if toc_entries:
        print(f"Оглавление: узлов {len(toc_entries)}, привязано к строке {toc_anchored}, "
              f"с точностью до страницы {issues['toc_page_only']}")
    print(f"Записано: {d['output']}/cards.jsonl")
    print("\nДальше обязательно: qa_report.py — до любой выгрузки.")
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="каталог книги books/<book-id>")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--meta", required=True, help="JSON с выходными данными книги")
    ap.add_argument("--pdf", help="исходный PDF (для оглавления и хеша), если не в work/pages_meta.json")
    a = ap.parse_args()

    prof = P.load_profile(a.profile)
    with open(a.meta, encoding="utf-8") as f:
        meta = json.load(f)
    pmeta_path = os.path.join(a.book, "work", "pages_meta.json")
    pdf = a.pdf
    if not pdf and os.path.exists(pmeta_path):
        pdf = json.load(open(pmeta_path, encoding="utf-8")).get("source_pdf")
    build(a.book, prof, meta, pdf)


if __name__ == "__main__":
    main()
