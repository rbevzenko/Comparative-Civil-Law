#!/usr/bin/env python3
"""Починка НОМЕРА ГЛАВЫ в составном номере заголовка.

    python scripts/fix_chapter_prefix.py --book <каталог> \
        --chapter '^Chapter\\s+(\\d{1,2})\\s*$' \
        --heading '^(\\d{1,2})((?:\\.\\d{1,2})*\\.\\d{1,2})(?=\\s+[A-Z]|$)' \
        [--size-min 17] [--size-max 45] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

У скана OCR систематически ошибается на ПЕРВОЙ цифре заголовка: у Dixon,
Modern Land Law «7.3 Legal and Equitable Easements» читается как «1.3», а
«11.2 … in Unregistered Land» — как «1.2». Номер внутри главы при этом
прочитан верно. В корпусе это даёт дубли адреса (три разных раздела с
адресом «1.3») и разрывы нумерации: разделы чужих глав валятся в ряд
первой главы.

Номер главы при этом известен точно: он стоит отдельной строкой на её
первой полосе («Chapter 7»). Скрипт ведёт счёт текущей главы по этим
строкам и переписывает первую цифру у каждого заголовка на неё.

Трогаются ТОЛЬКО строки, похожие на заголовок единицы: подходят под
`--heading` и попадают в полосу кегля. Перекрёстная ссылка в тексте под это
не подходит и остаётся как есть.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter", required=True, help="паттерн строки с номером главы")
    ap.add_argument("--heading", required=True, help="паттерн заголовка: группа 1 — номер главы")
    ap.add_argument("--size-min", type=float)
    ap.add_argument("--size-max", type=float)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    ch_rx = re.compile(a.chapter)
    hd_rx = re.compile(a.heading)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    cur = None
    fixed = seen = 0
    sample = []
    for pg in pages:
        for ln in pg.get("lines") or []:
            t = (ln.get("text") or "").strip()
            m = ch_rx.match(t)
            if m:
                cur = m.group(1)
                seen += 1
                continue
            if cur is None:
                continue
            size = ln.get("size")
            if a.size_min is not None and (size is None or size < a.size_min):
                continue
            if a.size_max is not None and (size is None or size > a.size_max):
                continue
            m = hd_rx.match(t)
            if not m or m.group(1) == cur:
                continue
            if len(sample) < 6:
                sample.append((pg["pdf_page"], t[:55], cur))
            if not a.dry_run:
                ln["text"] = cur + t[m.end(1):]
            fixed += 1

    print(f"глав найдено: {seen}, заголовков исправлено: {fixed}")
    for pno, before, ch in sample:
        print(f"  f{pno}: {before!r} → глава {ch}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
