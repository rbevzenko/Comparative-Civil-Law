#!/usr/bin/env python3
"""Печатное оглавление этой книги → work/toc.json.

    python parse_toc.py --pdf <файл> --book <каталог> [--pages 11-20] [--dry-run]

Общий `toc_parse.py` на этой книге даёт два узла из двухсот. Причина не в
разборе, а в сборке строк: у оглавления две колонки цифр («Rz» и «Seite»),
и на скане они регулярно уезжают в собственную строку —

    x 368.6 | 3. Verbrauchbare - unverbrauchbare Sachen . . . . . . 1/16 7
    x 369.7 | 5. Nebensachen . . . . . . . . . . . . . . . . . . . . . . .
    x1548.7 | 8

Заголовок и его страница оказываются разными строками, пара распадается, и
привязывать нечего.

Здесь строки собираются заново по вертикали: правая колонка (x > 1300)
приклеивается к ближайшему по высоте заголовку. Уровень берётся из отступа —
у этого оглавления он дискретный и чистый: 215 pt у частей и параграфов,
310-325 у римских, 365-375 у арабских, 420-425 у буквенных. Маркер служит
проверкой, а не источником: римская «I.» на скане regularly читается как
«1.», и по одному маркеру узел уехал бы на два уровня вниз.

Номер страницы — ПОСЛЕДНЕЕ число строки. Предпоследнее вида «1/16» — это
номер единицы, он в иерархию не идёт: у карточки он и так свой.
"""

import argparse
import json
import os
import re
import statistics

RIGHT_COLUMN = 1300.0        # правее — колонки «Rz» и «Seite»
ROW_TOL = 34.0               # pt: разброс базовой линии внутри одной строки
LEADERS = re.compile(r"[\s.·]{4,}")
TAIL = re.compile(r"(?:(\d{1,3}/\d{1,3})\s*)?(\d{1,3})\s*$")

# Уровень: часть, параграф и буквенная рубрика различаются МАРКЕРОМ — по
# отступу их не разделить, все три стоят у левого края (212-238 pt). Глубже
# наоборот: там маркер портится распознаванием (римская «I.» читается как
# «1.»), и уровень надёжнее берётся из отступа.
DEEP_LEVELS = [(0, 350, 3), (350, 400, 4), (400, 9999, 5)]
MARKERS = [
    (re.compile(r"^(Erster|Zweiter|Dritter|Vierter|Fünfter)\s+Teil\b"), "part", 0),
    (re.compile(r"^§\s*(\d{1,3})\."), "paragraph", 1),
    (re.compile(r"^([IVXL]{1,5})\."), "roman", 2),
    (re.compile(r"^([A-ZÄÖÜ])\."), "upper", 2),
    (re.compile(r"^(\d{1,2})\."), "digit", 3),
    (re.compile(r"^([a-z])\)"), "lower", 4),
]


def rows_of(page):
    """Слова страницы → строки по вертикальной близости."""
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    rows, cur = [], []
    for w in words:
        if cur and w["top"] - cur[0]["top"] > ROW_TOL:
            rows.append(cur)
            cur = []
        cur.append(w)
    if cur:
        rows.append(cur)
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def classify(text, x0):
    for rx, name, _ in MARKERS:
        m = rx.match(text)
        if m:
            return name, m.group(1) if m.lastindex else None
    return None, None


def depth_of(marker, x0):
    if marker == "part":
        return 0
    if marker == "paragraph":
        return 1
    if marker == "upper":
        return 2
    for lo, hi, d in DEEP_LEVELS:
        if lo <= x0 < hi:
            return d
    return 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--pages", default="11-20")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pdfplumber

    lo, hi = (int(x) for x in a.pages.split("-"))
    entries, orphan_numbers, source_pages = [], 0, list(range(lo, hi + 1))

    with pdfplumber.open(a.pdf) as pdf:
        for pno in source_pages:
            page = pdf.pages[pno - 1]
            rows = rows_of(page)
            titles = [r for r in rows if r[0]["x0"] < RIGHT_COLUMN]
            numbers = [r for r in rows if r[0]["x0"] >= RIGHT_COLUMN]

            # Правая колонка приклеивается к ближайшему по высоте заголовку.
            for nrow in numbers:
                y = nrow[0]["top"]
                near = min(titles, key=lambda r: abs(r[0]["top"] - y), default=None)
                if near is None or abs(near[0]["top"] - y) > ROW_TOL * 2:
                    orphan_numbers += 1
                    continue
                near.extend(nrow)

            for row in titles:
                raw = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
                text = LEADERS.sub(" ", raw).strip()
                if len(text) < 4:
                    continue
                marker, number = classify(text, row[0]["x0"])
                if marker is None:
                    continue
                m = TAIL.search(text)
                printed = int(m.group(2)) if m else None
                # Хвост «6/1 117» — это номер единицы и страница. В иерархию
                # он не идёт: у карточки её номер и так свой. Чистить надо
                # именно `raw` — extract.py показывает его, а не `title`.
                display = LEADERS.sub(" ", text[: m.start()] if m else text).strip(" .·")
                title = re.sub(r"^(?:§\s*\d{1,3}\.|[IVXL]{1,5}\.|[A-ZÄÖÜ]\.|\d{1,2}\.|[a-z]\)|"
                               r"(?:Erster|Zweiter|Dritter|Vierter|Fünfter)\s+Teil:?)\s*", "", display)
                depth = depth_of(marker, row[0]["x0"])
                entries.append({"depth": depth, "marker": marker, "number": number,
                                "title": title.strip(), "printed_page": printed,
                                "pdf_page": pno, "raw": display[:160],
                                "rel_x": round(row[0]["x0"])})

    # У частей в этом оглавлении своей страницы нет — она стоит только у
    # первого параграфа под ними. Пустую страницу оставлять нельзя: extract.py
    # сортирует узлы по ней и падает на None. Наследуем ближайшую следующую:
    # часть начинается там же, где её первый параграф.
    nxt = None
    for e in reversed(entries):
        if e["printed_page"] is None:
            e["printed_page"] = nxt
            e["page_inherited"] = True
        else:
            nxt = e["printed_page"]
    entries = [e for e in entries if e["printed_page"] is not None]

    by_depth = {}
    for e in entries:
        by_depth.setdefault(e["depth"], []).append(e["rel_x"])
    print(f"узлов оглавления: {len(entries)}, страниц оглавления: {len(source_pages)}")
    print(f"строк правой колонки без пары: {orphan_numbers}")
    for d in sorted(by_depth):
        print(f"  уровень {d}: узлов {len(by_depth[d]):3d}, медианный отступ "
              f"{statistics.median(by_depth[d]):.0f} pt")
    missing = [e for e in entries if e["printed_page"] is None]
    print(f"узлов без номера страницы: {len(missing)}")
    for e in entries[:6]:
        print(f"  d{e['depth']} {e['marker']:9s} с.{e['printed_page']} | {e['title'][:56]}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return

    path = os.path.join(a.book, "work", "toc.json")
    json.dump({"source_pages": len(source_pages), "entries": entries,
               "levels": {"median_x0": {str(d): statistics.median(v) for d, v in by_depth.items()}},
               "marker_conflicts": [], "method": "printed-toc/two-column"},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Записано: {path}")
    print("Дальше: extract.py — он привяжет узлы к строкам тела")


if __name__ == "__main__":
    main()
