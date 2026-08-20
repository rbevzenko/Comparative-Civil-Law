#!/usr/bin/env python3
"""Полосы концевых сносок → аппарат сносок.

    python scripts/endnotes_to_notes.py --book <каталог> \
        --size-min 10.5 --size-max 11.1 [--share 0.9] [--numbered 0.3] [--dry-run]

Запускать ПОСЛЕ pages_digital.py (и detab_lines.py) и ДО extract.py.

`split_footnotes` в pages_digital умеет отделять сноски, СТОЯЩИЕ ВНИЗУ СВОЕЙ
полосы. У Davies, Principles of Modern Company Law (Sweet & Maxwell, 11th
ed.) сносок внизу полосы нет вовсе: они собраны в конец главы и занимают
там целые полосы подряд, кеглем 10.8 против 14.4 у тела.

Скрипт находит такие полосы и целиком переносит их строки в аппарат.
Признаков два, и оба нужны: доля строк нужного кегля (`--share`) и доля
строк, начинающихся с номера (`--numbered`). Одного кегля мало — целая
полоса цитаты петитом выглядит так же, а номеров в ней нет.

Опознанный блок потом разрастается на соседей: его первая полоса бывает
почти сплошным продолжением предыдущей сноски и по доле номеров не
проходит (у Davies на f655 номером начинаются 12 строк из 48). Соседство с
уже опознанной полосой — признак надёжнее доли.

Дальше сноски раскладываются по карточкам знаком в тексте
(`attach_notes_by_marker.py`): на полосе концевых сносок единиц нет, и
штатная привязка «сноска на той же полосе, что знак» тут бессмысленна.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re

MARKER = re.compile(r"^(\d{1,4})[\s.]")


def build_notes(lines, page):
    notes, cur = [], None
    for ln in lines:
        t = (ln.get("text") or "").strip()
        if not t:
            continue
        m = MARKER.match(t)
        if m:
            if cur:
                notes.append(cur)
            cur = {"number": int(m.group(1)), "text": t[m.end():].strip(), "page": page}
            continue
        if cur is None:
            continue
        cur["text"] = (cur["text"] + " " + t).strip()
    if cur:
        notes.append(cur)
    return [n for n in notes if n["text"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--size-min", type=float, required=True)
    ap.add_argument("--size-max", type=float, required=True)
    ap.add_argument("--share", type=float, default=0.9,
                    help="доля строк нужного кегля, при которой полоса считается сносочной")
    ap.add_argument("--numbered", type=float, default=0.3,
                    help="доля строк, начинающихся с номера")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    def body(pg):
        return [l for l in (pg.get("lines") or []) if (l.get("text") or "").strip()]

    def petit(pg):
        lines = body(pg)
        if len(lines) < 4:
            return False
        small = [l for l in lines
                 if l.get("size") is not None and a.size_min <= l["size"] <= a.size_max]
        return len(small) / len(lines) >= a.share

    chosen = set()
    for i, pg in enumerate(pages):
        if not petit(pg):
            continue
        lines = body(pg)
        numbered = sum(1 for l in lines if MARKER.match((l.get("text") or "").strip()))
        if numbered / len(lines) >= a.numbered:
            chosen.add(i)

    # Блок концевых сносок идёт подряд, и его первая полоса бывает почти
    # сплошным продолжением предыдущей сноски: у Davies на f655 номером
    # начинаются 12 строк из 48, то есть четверть, и по доле номеров полоса
    # не проходит. Соседство с уже опознанной полосой — признак надёжнее
    # доли: набор кеглем сносок и вплотную к блоку сносок.
    grown = True
    while grown:
        grown = False
        for i, pg in enumerate(pages):
            if i in chosen or not petit(pg):
                continue
            if (i - 1) in chosen or (i + 1) in chosen:
                chosen.add(i)
                grown = True

    moved_pages = moved_lines = built = 0
    sample = []
    for i, pg in enumerate(pages):
        if i not in chosen:
            continue
        lines = body(pg)
        notes = build_notes(lines, pg.get("printed_page") or pg["pdf_page"])
        if len(sample) < 3:
            sample.append((pg["pdf_page"], len(lines), [(n["number"], n["text"][:40]) for n in notes[:2]]))
        moved_pages += 1
        moved_lines += len(lines)
        built += len(notes)
        if a.dry_run:
            continue
        pg["note_lines"] = (pg.get("note_lines") or []) + lines
        pg["notes"] = (pg.get("notes") or []) + notes
        pg["lines"] = []
        pg["endnotes_page"] = True

    print(f"полос концевых сносок: {moved_pages}, строк перенесено: {moved_lines}, сносок собрано: {built}")
    for pno, n, ex in sample:
        print(f"  f{pno}: строк {n}, первые сноски {ex}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
