#!/usr/bin/env python3
"""Разрезать строки по внутритекстовым пометкам вида «(p. 65)».

    python scripts/split_at_page_markers.py --book <каталог> \
        [--pattern '\\(p\\.\\s*(\\d{1,4})\\)'] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Зачем. Распечатки из Oxford Handbooks Online не несут колонцифры вовсе:
внизу полосы стоит «Page 12 of 39» — номер внутри ГЛАВЫ, а не книги.
Настоящие номера печатного издания вставлены прямо в текст пометкой
«(p. 65)» там, где в книге кончалась страница.

Пометка стоит В СЕРЕДИНЕ строки, и flow-режим extract.py её не увидит:
он берёт номер только в начале строки. Скрипт разрезает строку по
пометке, и дальше книга разбирается на карточки-страницы обычным
`mode: flow` с шаблоном `^\\(p\\.\\s*(\\d{1,4})\\)`.

Геометрия у обеих половин остаётся прежней: она нужна только для отделения
сносок и колонтитулов, а те к этому моменту уже сняты.
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
    ap.add_argument("--pattern", default=r"\(p\.\s*\d{1,4}\)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rx = re.compile(a.pattern)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    split = 0
    sample = []
    for pg in pages:
        out = []
        for ln in pg.get("lines") or []:
            t = ln.get("text") or ""
            m = rx.search(t)
            if not m or m.start() == 0:
                out.append(ln)
                continue
            head, tail = t[:m.start()].strip(), t[m.start():].strip()
            if not head or not tail:
                out.append(ln)
                continue
            out.append(dict(ln, text=head))
            out.append(dict(ln, text=tail))
            split += 1
            if len(sample) < 5:
                sample.append((pg["pdf_page"], head[-40:], tail[:45]))
        if out:
            pg["lines"] = out

    print(f"строк разрезано по пометке страницы: {split}")
    for pno, head, tail in sample:
        print(f"  f{pno}: …{head!r}\n         + {tail!r}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in pages:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}\nДальше: extract.py")


if __name__ == "__main__":
    main()
