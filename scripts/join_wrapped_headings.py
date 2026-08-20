#!/usr/bin/env python3
"""Сборка заголовка, разорванного по ширине полосы, в одну строку.

    python scripts/join_wrapped_headings.py --book <каталог> \
        --size-min 15.5 --size-max 18.5 [--max-gap 1.6] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

В режиме heading единицей становится КАЖДАЯ строка нужного кегля. Заголовок,
не поместившийся в строку, режется на две единицы, и вторая уносит с собой
весь текст раздела:

    «Liability of the assignee landlord and tenant on the»   ← карточка без текста
    «covenants»                                              ← карточка с текстом

Скрипт склеивает подряд идущие строки ОДНОГО кегля, стоящие вплотную одна
под другой, в одну строку. Порог `--max-gap` — расстояние между базовыми
линиями в долях высоты строки: два разных заголовка подряд в книге
разделены хотя бы абзацем, а перенос внутри заголовка идёт со стандартным
интерлиньяжем.

Равенство кегля обязательно: у Duddington подзаголовок кеглем 16 стоит
вплотную под заголовком кеглем 18 («— Chapter summary: putting it all
together» и «Test yourself»), и без этого условия они склеиваются в один.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--size-min", type=float, required=True)
    ap.add_argument("--size-max", type=float, required=True)
    ap.add_argument("--max-gap", type=float, default=1.6,
                    help="зазор между строками в долях высоты строки")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    joined = 0
    sample = []
    for pg in pages:
        lines = pg.get("lines") or []
        out = []
        for ln in lines:
            size = ln.get("size")
            fits = size is not None and a.size_min <= size <= a.size_max
            if out and fits:
                prev = out[-1]
                psize = prev.get("size")
                pfits = psize is not None and a.size_min <= psize <= a.size_max
                h = max(1.0, prev.get("bottom", 0) - prev.get("top", 0))
                gap = ln.get("top", 0) - prev.get("top", 0)
                same_size = pfits and abs(psize - size) <= 0.3
                if same_size and 0 < gap <= a.max_gap * h:
                    if len(sample) < 5:
                        sample.append((pg["pdf_page"], prev["text"][:55], ln["text"][:35]))
                    prev["text"] = (prev["text"].rstrip() + " " + ln["text"].lstrip()).strip()
                    prev["bottom"] = max(prev.get("bottom", 0), ln.get("bottom", 0))
                    prev["x1"] = max(prev.get("x1", 0), ln.get("x1", 0))
                    prev["words"] = (prev.get("words") or []) + (ln.get("words") or [])
                    joined += 1
                    continue
            out.append(ln)
        pg["lines"] = out

    print(f"склеено переносов заголовка: {joined}")
    for pno, b, c in sample:
        print(f"  f{pno}: {b!r} + {c!r}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
