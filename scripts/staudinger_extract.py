#!/usr/bin/env python3
"""Разбор распечатки онлайн-Staudinger на карточки «§ N Rn M».

    python scripts/staudinger_extract.py --book books/<id> --pdf файл.pdf \
        [--pages 1-200] [--dry-run]

ЗАЧЕМ ОТДЕЛЬНО ОТ beck_extract. Платформа другая (samson / Otto Schmidt),
и устроено всё иначе:

  * заголовок задания стоит в НАЧАЛЕ параграфа, а не в конце. Опознавательный
    знак — строка Zitiervorschlag: «Staudinger/Klumpp (2021) BGB § 104».
    В ней разом комментатор, год Neubearbeitung и параграф, то есть всё, что
    нужно для ссылки;
  * СНОСОК НЕТ. Staudinger даёт ссылки прямо в тексте, аппарата внизу полосы
    у него не бывает, и отделять нечего;
  * Randnummer стоит ПЕРВЫМ словом абзаца, на левом поле (x0 ≈ 31 при полосе,
    начинающейся с 65,7), а не последним словом строки справа;
  * контурного текста здесь нет — проверено на двух файлах и 4 271 длинной
    строке, все дыры в координатах оказались висячим номером, отточием
    оглавления и колонтитулом. Распознавание не нужно.
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P

from beck_extract import NUM_ONLY, join_hyphens, norm, read_lines

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")

# Строка Zitiervorschlag — единственный надёжный признак начала параграфа.
# Ярлык перед ней бывает и по-немецки, и по-английски («Zitiervorschlag:»,
# «Suggested citation:»), а у части файлов платформа переводит вообще всю
# шапку («Factory:» вместо «Werk:», «Author:» вместо «Autor:»). Поэтому ярлык
# берётся любой, лишь бы за ним стояло «Staudinger/».
#
# Сама ссылка бывает двух видов:
#   Staudinger/Klumpp (2021) BGB § 104
#   Staudinger/Schilken (2024) Vorbemerkungen zu §§ 164-181
# и второй нельзя терять: Vorbemerkungen — такая же единица цитирования, как
# параграф, и в них лежит вся общая часть института.
CITE_PAR = re.compile(
    r"^(?:[^:]{0,40}:\s*)?Staudinger/\s*(?P<bearb>[^()]{1,60}?)\s*\((?P<year>\d{4})\)\s*"
    r"(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*)\s*§+\s*(?P<par>\d+[a-zä]?)")
CITE_VOR = re.compile(
    r"^(?:[^:]{0,40}:\s*)?Staudinger/\s*(?P<bearb>[^()]{1,60}?)\s*\((?P<year>\d{4})\)\s*"
    r"(?:(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*)\s+)?"
    # «Vorbemerkungen zu §§ 164-181», «Vorbemerkung zu §§ 158–163» и английский
    # перевод той же строки — «Preliminary remarks to §§ 116». Три файла из
    # девятнадцати давали ноль карточек ровно из-за этих написаний.
    r"(?P<vorbem>Vorbem(?:erkung(?:en)?)?|Preliminary\s+remarks?)\s*(?:zu|to)?\s*"
    r"§+\s*(?P<par>\d+[a-zä]?(?:\s*(?:-|–|ff)\s*\d*[a-zä]?)?)")

LABEL = re.compile(
    r"^(Werk|Factory|Autor|Author|Redaktor|Editor|Werksstand|Factory status|"
    r"Updatestand|Update status|Quelle|Source)\s*(status)?:")

JUNK = [
    re.compile(r"^samson-[a-z0-9]+", re.I),
    re.compile(r"^\d{2}[./]\d{2}[./]\d{4},\s*\d{2}:\d{2}"),
    re.compile(r"^©\s*Otto Schmidt"),
    LABEL,
]

def body_left(lines):
    """Левый край полосы набора — по длинным строкам без висячего номера."""
    lefts = []
    for ln in lines:
        words = ln.get("words") or []
        if len(ln["text"]) > 40 and words:
            first = min(words, key=lambda w: w["x0"])
            if not NUM_ONLY.fullmatch(first["text"].strip()):
                lefts.append(ln["x0"])
    return statistics.median(lefts) if len(lefts) >= 4 else None


def pull_hanging_numbers(lines):
    """Снять висячие Randnummern с начала абзацев.

    Номер стоит ПЕРВЫМ словом и отделён от текста заметным отступом: он
    висит на поле слева от полосы. Отступ и есть признак — иначе под правило
    попадёт всякий абзац закона, начинающийся с цифры («1. wer nicht das
    siebente Lebensjahr vollendet hat»), но там после цифры стоит точка и
    отступа нет.
    """
    edge = body_left(lines)
    if edge is None:
        return
    for ln in lines:
        words = sorted(ln.get("words") or [], key=lambda w: w["x0"])
        if len(words) < 2:
            continue
        first, second = words[0], words[1]
        if (NUM_ONLY.fullmatch(first["text"].strip())
                and first["x1"] <= edge - 2
                and second["x0"] >= first["x1"] + 8):
            ln["rn"] = int(first["text"])
            ln["words"] = words[1:]
            ln["text"] = norm(" ".join(w["text"] for w in words[1:]))
            ln["x0"] = second["x0"]


def split_sections(lines):
    """Разрезать поток строк по строкам Zitiervorschlag.

    Она стоит в начале параграфа, поэтому всё, что идёт ПОСЛЕ неё и до
    следующей такой строки, — текст этого параграфа. Хвост перед первой
    ссылкой (титул распечатки) выбрасывается.
    """
    blocks, cur, cite = [], [], None
    for ln in lines:
        m = CITE_VOR.match(ln["text"]) or CITE_PAR.match(ln["text"])
        if m:
            if cite:
                blocks.append({"cite": cite, "lines": cur})
            cite, cur = m.groupdict(), []
            continue
        if cite is not None:
            cur.append(ln)
    if cite:
        blocks.append({"cite": cite, "lines": cur})

    # Длинный параграф платформа печатает кусками, и строку Zitiervorschlag
    # ставит в начале КАЖДОГО. У § 434 их сорок девять. Если считать каждый
    # кусок отдельным параграфом, у него выходит сорок девять «вступлений» с
    # одинаковым external_id — приёмник затрёт их друг другом, и от § 434
    # останется последний обрывок. Куски одного параграфа склеиваются в
    # порядке файла.
    merged, order = {}, []
    for b in blocks:
        c = b["cite"]
        key = ((c.get("vorbem") or "").strip(), c["par"])
        if key not in merged:
            merged[key] = {"cite": c, "lines": []}
            order.append(key)
        merged[key]["lines"].extend(b["lines"])
    return [merged[k] for k in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages")
    ap.add_argument("--jurisdiction", default="DE")
    ap.add_argument("--language", default="de")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = P.book_dirs(a.book)
    meta_path = os.path.join(a.book, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    book_id = meta.get("book_id") or os.path.basename(a.book.rstrip("/"))

    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        print(f"полос в файле: {len(pdf.pages)}, разбирается: {len(idx)}", flush=True)
        lines = read_lines(pdf, idx)
    lines = [ln for ln in lines if not any(rx.search(ln["text"]) for rx in JUNK)]
    print(f"строк после чистки: {len(lines)}", flush=True)

    blocks = split_sections(lines)
    print(f"параграфов: {len(blocks)}", flush=True)

    warn = Counter()
    digest = P.sha256_file(a.pdf)
    cards, texts, offset = [], [], 0
    for blk in blocks:
        c = blk["cite"]
        pull_hanging_numbers(blk["lines"])
        marks = [k for k, ln in enumerate(blk["lines"]) if ln.get("rn") is not None]
        vor = (c.get("vorbem") or "").strip()
        sec = ("Vorbem " + c["par"]) if vor else c["par"]
        if not marks:
            warn["параграф без Randnummern"] += 1
            continue
        head = blk["lines"][:marks[0]]
        pieces = [(0, head)] if head else []
        for j, k in enumerate(marks):
            end = marks[j + 1] if j + 1 < len(marks) else len(blk["lines"])
            pieces.append((blk["lines"][k]["rn"], blk["lines"][k:end]))
        for num, chunk in pieces:
            text = join_hyphens("\n".join(ln["text"] for ln in chunk).strip())
            if not text:
                continue
            gesetz = (c.get("gesetz") or "BGB").strip()
            address = (f"{gesetz} Vorbemerkungen zu §§ {c['par']}" if vor
                       else f"{gesetz} § {c['par']}")
            address += f" Rn {num}" if num else " Schrifttum und Übersicht"
            start = offset
            texts.append(text)
            offset += len(text) + 1
            cards.append({
                "external_id": f"{book_id}:rn:{sec}/{num}",
                "id": f"{book_id}-rn{sec}-{num}",
                "book_id": book_id,
                "unit": "Rn", "unit_type": "Rn", "unit_number": str(num), "number": num,
                "section": sec,
                "address": address,
                "citation": f"Staudinger/{c['bearb'].strip()} ({c['year']}) {address}",
                "text": text,
                "hierarchy": [f"§ {c['par']}"],
                "footnotes": [],
                "statutory_refs": [], "cross_refs": [], "contains_also": [],
                "institute": None, "concept_ids": [],
                "source": {k: meta.get(k) for k in ("authors", "title", "edition", "year", "publisher")},
                "jurisdiction": meta.get("jurisdiction") or a.jurisdiction,
                "language": meta.get("language") or a.language,
                "page_start": chunk[0]["pdf_page"], "page_end": chunk[-1]["pdf_page"],
                "printed_page_start": None, "printed_page_end": None,
                "char_start": start, "char_end": offset - 1,
                "bbox": [],
                "source_file": os.path.basename(a.pdf),
                "source_sha256": digest,
                "method": "digital",
                "detection_mode": "поле" if num else "вступление",
                "detection_evidence": {"bearbeiter": c["bearb"].strip()},
                "profile": "staudinger-online-v1",
                "chunk_version": P.SCHEMA_VERSION,
            })

    # Один и тот же параграф в файле бывает напечатан дважды: скачивали
    # внахлёст. Тогда у каждой Randnummer оказывается две карточки с
    # ОДИНАКОВЫМ external_id, и приёмник затрёт одну другой — какой именно,
    # зависит от порядка. Оставляем более длинный вариант: короткий обычно
    # обрывок, начатый на предыдущей полосе.
    best = {}
    for c in cards:
        k = c["external_id"]
        if k not in best or len(c["text"]) > len(best[k]["text"]):
            best[k] = c
    if len(best) < len(cards):
        print(f"снято повторов внутри файла: {len(cards) - len(best)}")
    cards = [c for c in cards if c is best.get(c["external_id"])]

    print(f"карточек: {len(cards)}")
    for k, v in warn.most_common():
        print(f"  ВНИМАНИЕ: {k}: {v}")
    if a.dry_run:
        return
    P.atomic_write(os.path.join(d["work"], "book.txt"), "\n".join(texts))
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf), "source_sha256": digest,
        "branch": "staudinger", "method": "digital", "profile": "staudinger-online-v1",
        "pages_requested": len(idx), "pages_built": len(idx), "pages_empty": 0,
        "schema_version": P.SCHEMA_VERSION,
    })
    P.write_jsonl(os.path.join(d["output"], "cards.jsonl"), cards)
    print(f"Записано: {d['output']}/cards.jsonl")


if __name__ == "__main__":
    main()
