#!/usr/bin/env python3
"""Замена табуляции в текстовом слое на пробел.

    python scripts/detab_lines.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО остальных шагов.

В части издательских PDF слова разделены не пробелом, а табуляцией нулевой
ширины. У Treitel (Peel), The Law of Contract, 14th ed., так набрано 63%
строк тела: «giving\\trise\\tto\\tobligations». Ширины у такого символа нет,
поэтому pipelib не видит здесь границы слова и склеивает всё в одно.

В карточке это ломает и чтение, и поиск по фразе, а в разборе сносок — знак
сноски: «1\\t\\tFriedmann 119 L.Q.R. 68» не подходит под шаблон «номер, пробел,
текст», и вся полоса сносок ложится одним блоком без номера.
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

WS = re.compile(r"[\t   ]+")


def clean(s, subs=()):
    for old, new in subs:
        s = s.replace(old, new)
    return re.sub(r" {2,}", " ", WS.sub(" ", s)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--map", action="append", default=None, metavar="ИЗ=В",
                    help="дополнительная замена в тексте строки, можно повторять; "
                         "у Duddington маркер списка «■■» заменяется на тире")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    subs = []
    for item in a.map or []:
        old, _, new = item.partition("=")
        if not old:
            raise SystemExit(f"--map ждёт «ИЗ=В», получено {item!r}")
        subs.append((old, new))

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    touched = words = 0
    sample = []
    for pg in pages:
        for key in ("lines", "note_lines"):
            for ln in pg.get(key) or []:
                before = ln.get("text") or ""
                after = clean(before, subs)
                if after != before:
                    if len(sample) < 4:
                        sample.append((pg["pdf_page"], before[:60], after[:60]))
                    ln["text"] = after
                    touched += 1
                for w in ln.get("words") or []:
                    t = clean(w.get("text") or "", subs)
                    if t != w.get("text"):
                        w["text"] = t
                        words += 1

    print(f"строк исправлено: {touched}, слов: {words}")
    for pno, b, c in sample:
        print(f"  f{pno}: {b!r}\n      → {c!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
