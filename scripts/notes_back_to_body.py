#!/usr/bin/env python3
"""Возврат в тело полосы строк, ошибочно снятых как сноски.

    python scripts/notes_back_to_body.py --book <каталог> --size-max 7.9 [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

split_footnotes отделяет сноски по кеглю и полосе. Когда на странице ДВА
разных аппарата, правило по кеглю снимает оба, а нужен только один.

У Smith, Property Law: Cases and Materials (Pearson, 6th ed.) авторские
сноски набраны кеглем 8.0 и стоят под чертой внизу полосы; но у каждого
извлечения из решения есть ещё СОБСТВЕННЫЙ аппарат римскими цифрами кеглем
7.5 — это сноски самого судьи, часть цитируемого текста. Порог 8.2,
необходимый, чтобы поймать авторские сноски, забирает и их: 1950 строк на
466 страницах. Номер у них римский, поэтому в `notes` они не попадают
вовсе — текст просто пропадает.

Скрипт возвращает в конец `lines` те строки из `note_lines`, чей кегль
меньше порога, и пересобирает `notes` из оставшихся. Порядок сохраняется, а
место — конец полосы — там же, где эти строки и напечатаны.

С `--rebuild-all` аппарат пересобирается на ВСЕХ страницах, а не только на
тронутых. Это нужно, когда до этого шага по note_lines прошёлся
inline_superscripts.py: он уносит в тело знаки сноски, залетевшие в нижнюю
полосу, а `notes`, собранный на разборе страницы, про это не знает и
остаётся со ссылками на уже унесённые строки.

Знак сноски порогом кегля не отличить: у Smith авторский знак набран
кеглем 4.8, судейский — 4.5. Отличается написание: авторский знак
арабский, судейский римский. Поэтому строка из одних ЦИФР остаётся в
аппарате независимо от кегля — иначе номера уезжают в тело, а `notes`
собирается пустым.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re

MARKER = re.compile(r"^\s*(\d{1,3})[\.\)]?\s*$")
DIGITS_ONLY = re.compile(r"^[\d\s\.\)]+$")


def rebuild_notes(note_lines, page=None):
    """Простая пересборка: номер отдельной строкой, дальше текст до следующего."""
    notes = []
    cur = None
    for ln in note_lines:
        t = (ln.get("text") or "").strip()
        if not t:
            continue
        m = MARKER.match(t)
        if m:
            if cur:
                notes.append(cur)
            cur = {"number": int(m.group(1)), "text": "", "page": page}
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
    ap.add_argument("--size-max", type=float, required=True,
                    help="строки сносок МЕНЬШЕ этого кегля возвращаются в тело")
    ap.add_argument("--rebuild-all", action="store_true",
                    help="пересобрать notes на ВСЕХ страницах, а не только на тронутых")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    moved = 0
    touched = 0
    for pg in pages:
        nl = pg.get("note_lines") or []
        if not nl:
            if a.rebuild_all and not a.dry_run:
                pg["notes"] = []
            continue
        back = [n for n in nl
                if n.get("size") is not None and n["size"] < a.size_max
                and not DIGITS_ONLY.match((n.get("text") or "").strip())]
        if not back:
            if a.rebuild_all and not a.dry_run:
                pg["notes"] = rebuild_notes(nl, pg.get("printed_page"))
            continue
        keep = [n for n in nl if n not in back]
        moved += len(back)
        touched += 1
        if a.dry_run:
            continue
        pg["lines"] = (pg.get("lines") or []) + back
        pg["note_lines"] = keep
        pg["notes"] = rebuild_notes(keep, pg.get("printed_page"))

    print(f"возвращено в тело строк: {moved} на {touched} страницах")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
