#!/usr/bin/env python3
"""Сращивание слов, разорванных на месте лигатуры.

    python scripts/fix_broken_ligatures.py --book <каталог> [--pair Th] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО остальных шагов.

Если во встроенном шрифте лигатура (Th, fi, fl, ffi, ffl) вынесена
отдельным глифом без карты в Unicode, извлечённый текст разрывает слово
ровно на ней: «Th e protection», «at fi rst», «which fl ew open». У Street
on Torts, 13th ed. таких разрывов около 0.22% знаков — примерно 1800 на
книгу, и слова «The», «first», «flew» в корпусе не находятся вовсе.

Сращивается и обломок-«слово» («Th e»), и хвост настоящего слова («defi
nitions»): глиф лигатуры стоит в середине, и разрыв приходится ровно на
него. Условие одно — следом идёт строчная буква. Требовать двух мало: «Th e» —
самый частый случай, и второй знак там пробел.
Слова, кончающиеся на эти сочетания и стоящие перед строчным словом, в
юридическом тексте не встречаются, а «craft as» (съеденная лигатура ft) не
трогается: ft в список не входит.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re

DEFAULT_PAIRS = ["Th", "ffi", "ffl", "fi", "fl"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pair", action="append", default=None,
                    help=f"обломок лигатуры; по умолчанию {' '.join(DEFAULT_PAIRS)}")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pairs = a.pair or DEFAULT_PAIRS
    # Обломок может быть и целым «словом» («Th e protection»), и хвостом
    # настоящего слова («defi nitions», «artifi cial», «diffi cult»): глиф
    # лигатуры стоит в середине, и разрыв приходится ровно на него.
    rx = re.compile(r"\b([A-Za-z]*(?:%s)) (?=[a-z])" % "|".join(re.escape(p) for p in pairs))

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    hits = 0
    sample = []
    for pg in pages:
        for key in ("lines", "note_lines"):
            for ln in pg.get(key) or []:
                for field in (ln, *(ln.get("words") or [])):
                    t = field.get("text") or ""
                    new, n = rx.subn(r"\1", t)
                    if n:
                        if len(sample) < 4 and field is ln:
                            sample.append((t[:60], new[:60]))
                        field["text"] = new
                        hits += n

    print(f"сращено разрывов: {hits}")
    for a_, b_ in sample:
        print(f"  было:  {a_!r}\n  стало: {b_!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
