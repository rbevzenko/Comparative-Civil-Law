#!/usr/bin/env python3
"""Отделение блока сносок, когда кегль его не выдаёт.

    python scripts/split_notes_by_chunk.py --book <каталог> \
        --chunk-start '^Goff & Jones' [--note-start '^(\\d{1,4})\\.\\s'] [--dry-run]

Запускать ПОСЛЕ pages_digital.py (с `footnotes.mode: none`) и ДО
fix_footnote_markers.py.

Штатное отделение сносок опирается на кегль или на положение внизу полосы.
У выгрузки Goff & Jones не работает ни то, ни другое: сноски набраны тем же
кеглем 10, что и тело, а блок сносок занимает целые полосы подряд — на такой
полосе «низа» нет, она вся сноски, и первые её строки вообще продолжают
сноску, начатую страницей раньше.

Зато у выгрузки есть куски: каждый раздел выгружен отдельно, со своей
пагинацией с единицы. Внутри куска порядок всегда один: сначала текст, потом
весь аппарат. Поэтому границей служит первая строка вида «N. », за которой в
том же куске идёт «N+1. » — дальше до конца куска всё сноски, сколько бы
полос они ни занимали.

Требовать, чтобы блок открывался единицей, нельзя: нумерация сносок здесь
сквозная по ГЛАВЕ, а не по разделу, и второй раздел начинает свои сноски с
тринадцатой. На живом прогоне такое требование находило блок в 36 кусках из
600. Пара подряд идущих номеров — признак не хуже: ни одно перечисление в
теле этой книги так не набрано.

Строка --chunk-start (заголовок выгрузки) сама в текст не идёт: скрипт
снимает её, использовав как границу.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--chunk-start", required=True, help="строка, открывающая кусок выгрузки")
    ap.add_argument("--note-start", default=r"^(\d{1,4})\.\s", help="строка, открывающая сноску")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    chunk_rx, note_rx = re.compile(a.chunk_start), re.compile(a.note_start)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    # Куски: последовательности полос между строками --chunk-start.
    chunks, cur = [], []
    for pg in pages:
        opens = any(chunk_rx.match((ln["text"] or "").strip()) for ln in pg.get("lines") or [])
        if opens and cur:
            chunks.append(cur)
            cur = []
        cur.append(pg)
    if cur:
        chunks.append(cur)

    moved = chunks_split = headers = 0
    for chunk in chunks:
        flat = [(pg, k, ln) for pg in chunk for k, ln in enumerate(pg.get("lines") or [])]
        for pg, k, ln in flat:
            if chunk_rx.match((ln["text"] or "").strip()):
                ln["_drop"] = True
                headers += 1
        nums = [(i, int(m.group(1))) for i, (_, _, ln) in enumerate(flat)
                if (m := note_rx.match((ln["text"] or "").strip()))]
        start = None
        for pos, (i, n) in enumerate(nums):
            if any(m == n + 1 for _, m in nums[pos + 1:]):
                start = i
                break
        if start is None:
            continue
        chunks_split += 1
        for pg, _, ln in flat[start:]:
            ln["_note"] = True
            moved += 1

    for pg in pages:
        body, notes = [], []
        for ln in pg.get("lines") or []:
            if ln.pop("_drop", False):
                continue
            (notes if ln.pop("_note", False) else body).append(ln)
        pg["lines"] = body
        pg["note_lines"] = (pg.get("note_lines") or []) + notes
        pg["notes"] = []

    print(f"кусков выгрузки: {len(chunks)}, с найденным блоком сносок: {chunks_split}")
    print(f"строк переведено в сноски: {moved}, снято заголовков выгрузки: {headers}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
