#!/usr/bin/env python3
"""Убрать из pages.jsonl строки по шаблону — без переразбора книги.

    python scripts/drop_junk_lines.py --book <каталог> \
        --pattern '\\s\\.\\s+\\d{1,2}-\\d{3}$' [--notes] [--dry-run]

Зачем отдельный скрипт. Мусорные шаблоны профиля (`junk.patterns`)
применяются, когда полоса кладётся в КЭШ. `pages_digital.py --skip-done`
собирает pages.jsonl из готового кэша и профиль заново не спрашивает —
значит, шаблон, добавленный после набора кэша, не сработает. Полный
переразбор Snell's Equity ради одной строки — сорок минут; этот скрипт
снимает её за секунду.

Дальше всё равно нужен extract.py: карточки собираются из pages.jsonl.

--dry-run печатает, что будет убрано, и файла не трогает. Пользоваться им
стоит всегда: шаблон, снявший строку тела книги, обнаружится только
пропуском в отчёте качества, и то не сразу.
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
    ap.add_argument("--pattern", required=True, action="append",
                    help="можно повторять; строка убирается по любому совпадению")
    ap.add_argument("--notes", action="store_true",
                    help="чистить и аппарат сносок (note_lines), не только тело")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rxs = [re.compile(p) for p in a.pattern]
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    keys = ["lines"] + (["note_lines"] if a.notes else [])
    dropped, sample = 0, []
    for pg in pages:
        for key in keys:
            rows = pg.get(key) or []
            kept = []
            for ln in rows:
                t = ln.get("text") or ""
                if any(rx.search(t) for rx in rxs):
                    dropped += 1
                    if len(sample) < 20:
                        sample.append((pg["pdf_page"], key, t[:95]))
                    continue
                kept.append(ln)
            if kept != rows:
                pg[key] = kept

    print(f"строк убрано: {dropped}")
    for pno, key, t in sample:
        print(f"  f{pno} {key}: {t!r}")
    if dropped > len(sample):
        print(f"  … и ещё {dropped - len(sample)}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in pages:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}\nДальше: extract.py")


if __name__ == "__main__":
    main()
