#!/usr/bin/env python3
"""Свести повторы между распечатками одного и того же комментария.

    python scripts/dedupe_beck_books.py books/de-mukobgb-* [--dry-run]

ЗАЧЕМ. Распечатки заказывались по диапазонам параграфов, и диапазоны
налезают друг на друга: «985-1011» и «986-1011» — это один и тот же кусок,
скачанный дважды. Внутри файла повторы схлопывает сам разборщик, между
файлами — некому: у каждой распечатки свой `book_id`, а значит и свой
`external_id`, и приёмник примет обе как разные фрагменты. В корпусе
получится § 986 Rn. 3 в двух экземплярах, и поиск будет показывать одно
место дважды.

Ключ — пара (параграф, Randnummer): она и есть адрес места в комментарии,
одинаковый в любой распечатке. Из совпавших остаётся САМАЯ ДЛИННАЯ: короткая
обычно обрывок задания, начатого на предыдущей полосе.

Отдельно снимаются карточки на диапазон («Rn. 6-8») — но только те, все
номера которых нашлись поодиночке хоть в какой-нибудь распечатке. Диапазон,
чьи номера больше нигде не разложены, остаётся: он единственный носитель
этого текста.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cards = {}
    for book in a.books:
        path = os.path.join(book, "output", "cards.jsonl")
        if not os.path.exists(path):
            print(f"пропущено (нет карточек): {book}")
            continue
        cards[book] = P.read_jsonl(path)
    if not cards:
        sys.exit("нечего сводить")

    singles = defaultdict(list)          # (§, Rn) → [(книга, индекс)]
    ranges = []
    for book, cs in cards.items():
        for i, c in enumerate(cs):
            if c.get("contains_also"):
                ranges.append((book, i))
            singles[(c["section"], c["number"])].append((book, i))

    drop = defaultdict(set)
    dup_pairs = 0
    for key, places in singles.items():
        if len(places) < 2:
            continue
        dup_pairs += 1
        best = max(places, key=lambda t: len(cards[t[0]][t[1]]["text"]))
        for p in places:
            if p != best:
                drop[p[0]].add(p[1])

    single_keys = {k for k, v in singles.items()
                   if any((b, i) not in drop[b] for b, i in v)}
    dropped_ranges = 0
    for book, i in ranges:
        c = cards[book][i]
        nums = [x["number"] for x in c["contains_also"]]
        if all((c["section"], n) in single_keys for n in nums):
            drop[book].add(i)
            dropped_ranges += 1

    total_before = sum(len(v) for v in cards.values())
    print(f"карточек всего: {total_before}")
    print(f"адресов, встретившихся больше одного раза: {dup_pairs}")
    print(f"карточек на диапазон, разложенных поодиночке: {dropped_ranges}")
    for book in sorted(cards):
        n = len(drop[book])
        if n:
            print(f"  {os.path.basename(book):<24} снимается {n} из {len(cards[book])}")
    print(f"останется: {total_before - sum(len(v) for v in drop.values())}")
    if a.dry_run:
        return
    for book, cs in cards.items():
        if not drop[book]:
            continue
        keep = [c for i, c in enumerate(cs) if i not in drop[book]]
        P.write_jsonl(os.path.join(book, "output", "cards.jsonl"), keep)
    print("карточки переписаны")


if __name__ == "__main__":
    main()
