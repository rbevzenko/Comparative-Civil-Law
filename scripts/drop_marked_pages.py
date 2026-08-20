#!/usr/bin/env python3
"""Снятие служебных полос, опознанных по строке-маркеру.

    python scripts/drop_marked_pages.py --book <каталог> --marker "Chapter Contents" [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

У Dixon, Modern Land Law каждая глава открывается собственным оглавлением:
«Chapter Contents», дальше «2.2 The Nature and Purpose of the System of
Registered Land 31». Эти строки неотличимы по виду от настоящих
заголовков — тот же номер, та же заглавная буква, — и дают 12 дублей
адреса и 44 разрыва в нумерации.

Отличает их полоса, на которой они стоят: на ней есть строка-маркер и нет
текста книги. Скрипт вычищает такие полосы целиком.
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
    ap.add_argument("--marker", action="append", required=True,
                    help="строка-маркер, можно повторять; сравнение без учёта регистра")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    marks = [m.lower() for m in a.marker]
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    hit = lines = 0
    sample = []
    for pg in pages:
        text = "\n".join((l.get("text") or "") for l in (pg.get("lines") or [])).lower()
        if not any(m in text for m in marks):
            continue
        hit += 1
        lines += len(pg.get("lines") or [])
        if len(sample) < 5:
            sample.append(pg["pdf_page"])
        if not a.dry_run:
            pg["lines"] = []
            pg["dropped_marked"] = True

    print(f"снято полос: {hit}, строк: {lines}")
    if sample:
        print("  первые: " + ", ".join(f"f{p}" for p in sample))
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
