#!/usr/bin/env python3
"""Склейка слов, разорванных переносом, прямо в готовых карточках.

    python scripts/join_hyphens_cards.py books/de-* [--dry-run]

Правило то же, что у немецких разборщиков (`join_hyphens` в
`scripts/beck_extract.py`), но применяется к `output/cards.jsonl` — там, где
книга разобрана ШТАТНЫМ конвейером и своего шага склейки у неё нет.

Слово, разорванное переносом, для поиска — два разных слова: «Grund-\\nnorm»
не найдётся ни по «Grundnorm», ни по одной из половин. У Stein/Jonas перенос
на каждой третьей строке.

Правило немецкое и на другие языки НЕ переносится: во французском дефис в
конце строки часто настоящий («celui-ci», «au-delà»), и склейка испортила бы
текст. Поэтому скрипт зовётся списком книг, а не по всему каталогу.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P

from beck_extract import join_hyphens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    total = 0
    for book in a.books:
        path = os.path.join(book, "output", "cards.jsonl")
        if not os.path.exists(path):
            continue
        cards = P.read_jsonl(path)
        n = 0
        for c in cards:
            new = join_hyphens(c["text"])
            if new != c["text"]:
                c["text"] = new
                n += 1
            for f in c.get("footnotes") or []:
                f["text"] = join_hyphens(f["text"])
        if n and not a.dry_run:
            P.write_jsonl(path, cards)
        if n:
            print(f"  {os.path.basename(book)}: карточек со склейкой {n} из {len(cards)}")
        total += n
    print(f"всего карточек поправлено: {total}")


if __name__ == "__main__":
    main()
