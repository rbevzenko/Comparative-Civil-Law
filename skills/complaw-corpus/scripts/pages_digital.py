#!/usr/bin/env python3
"""
Ветка A: цифровой PDF → модель страницы.

Usage:
    python pages_digital.py book.pdf --book books/<book-id> --profile profiles/x.yaml \
        [--pages 40-1200] [--skip-done]

Пишет постранично в cache/pages/page-NNNN.json и собирает work/pages.jsonl.
Постраничный кэш нужен не для скорости, а чтобы падение на странице 300
не заставляло начинать со страницы 1 (§16).

Порядок операций внутри страницы менять нельзя (§4, ветка A):
    очистка мусора → колонцифра → отделение сносок → строки тела.
Сноски собираются постранично ДО нарезки на единицы: их нумерация
сбрасывается на каждой странице, а единица идёт через разворот.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipelib as P

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")


def build_page(page, i, prof, junk_rx):
    chars = page.chars
    height, width = float(page.height), float(page.width)
    if not chars:
        return {"pdf_page": i + 1, "printed_page": None, "width": width, "height": height,
                "method": "digital", "lines": [], "note_lines": [], "notes": [],
                "empty": True}

    pp = prof.get("printed_page", {}) or {}
    jn = prof.get("junk", {}) or {}
    # Правка регистра включается профилем: она нужна только тем книгам, у
    # которых во встроенном шрифте перепутан ToUnicode, и молча портить
    # остальные нельзя.
    if (prof.get("case_repair") or "") == "width":
        chars = P.repair_case_by_width(chars)
    lines = P.chars_to_lines(chars)
    printed, head_i = P.detect_printed_page_line(lines, height, pp.get("band", 0.12),
                                                 pp.get("patterns"), pp.get("max_chars", 70))
    # Строка, в которой нашлась колонцифра, и есть колонтитул: снимаем именно
    # её, а не полосу вслепую. Полоса промахивается, когда колонтитул съезжает
    # на скане, и тогда номер страницы попадает в карточки как Randziffer.
    if head_i is not None:
        lines = [l for k, l in enumerate(lines) if k != head_i]
    lines = P.strip_bands(lines, height, jn.get("header_band"), jn.get("footer_band"))
    lines = P.strip_junk(lines, junk_rx, printed, height)
    body, note_lines = P.split_footnotes(lines, height, prof, "digital")
    return {
        "pdf_page": i + 1,
        "printed_page": printed,
        "width": width, "height": height,
        "method": "digital",
        "lines": body,
        "note_lines": note_lines,
        "notes": P.parse_notes(note_lines, printed or (i + 1)),
        "empty": not body,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--book", required=True, help="каталог книги books/<book-id>")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--pages", help="диапазон страниц файла, напр. 40-1200")
    ap.add_argument("--skip-done", action="store_true", help="не переделывать уже разобранные страницы")
    a = ap.parse_args()

    prof = P.load_profile(a.profile)
    junk_rx = P.compile_patterns(prof.get("junk", {}).get("patterns"))
    d = P.book_dirs(a.book)
    cache = os.path.join(d["cache"], "pages")
    os.makedirs(cache, exist_ok=True)

    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        done = 0
        for i in idx:
            path = os.path.join(cache, f"page-{i + 1:05d}.json")
            if a.skip_done and os.path.exists(path):
                done += 1
                continue
            P.write_json(path, build_page(pdf.pages[i], i, prof, junk_rx))
            done += 1
            if done % 50 == 0:
                print(f"  страниц разобрано: {done}/{len(idx)}", flush=True)

    # При --skip-done модель страницы собирается из ВСЕГО накопленного кэша,
    # а не только из запрошенного диапазона. Иначе второй заход по другим
    # страницам молча выбрасывает результат первого, и книга худеет на глазах.
    import json as _json
    wanted = sorted({i + 1 for i in idx} | (
        {int(n[5:10]) for n in os.listdir(cache) if n.startswith("page-") and n.endswith(".json")}
        if a.skip_done else set()))
    pages = []
    for pno in wanted:
        path = os.path.join(cache, f"page-{pno:05d}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                pages.append(_json.load(fh))

    P.write_jsonl(os.path.join(d["work"], "pages.jsonl"), pages)
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf),
        "source_sha256": P.sha256_file(a.pdf),
        "branch": "A",
        "method": "digital",
        "profile": prof.get("id"),
        "pages_requested": len(idx),
        "pages_built": len(pages),
        "pages_empty": sum(1 for p in pages if p.get("empty")),
        "schema_version": P.SCHEMA_VERSION,
    })
    print(f"Страниц в модели: {len(pages)}, пустых: {sum(1 for p in pages if p.get('empty'))}")
    print(f"Записано: {d['work']}/pages.jsonl")
    print("Дальше: extract.py")


if __name__ == "__main__":
    main()
