#!/usr/bin/env python3
"""Снятие карточек с повторяющимся адресом.

    python scripts/drop_duplicate_cards.py --book books/<id> [--keep last] [--dry-run]

Запускать ПОСЛЕ extract.py, до выгрузки.

`external_id` должен быть уникален: приёмник отвергает файл целиком, а не
отдельную карточку. Дубль адреса берётся из ложной единицы — номера,
прочитанного OCR посреди сноски или в оглавлении главы.

У Hanbury & Martin, Modern Equity таких три на 1025 карточек, и во всех трёх
ложная — РАННЯЯ: настоящий абзац идёт позже, а раньше стоит перекрёстная
ссылка на него. Поэтому по умолчанию остаётся последняя.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--keep", choices=["first", "last"], default="last")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    counts = Counter(c["external_id"] for c in cards)
    dupes = {k for k, v in counts.items() if v > 1}
    if not dupes:
        print("дублей адреса нет")
        return

    seen = Counter()
    keep = []
    dropped = []
    for c in cards:
        eid = c["external_id"]
        if eid not in dupes:
            keep.append(c)
            continue
        seen[eid] += 1
        take = seen[eid] == (1 if a.keep == "first" else counts[eid])
        (keep if take else dropped).append(c)

    print(f"дублей адреса: {len(dupes)}, снято карточек: {len(dropped)}")
    for c in dropped[:5]:
        print(f"  {c['address']} f{c.get('page_start')}: {(c.get('text') or '')[:60]!r}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in keep:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path} ({len(keep)} карточек)")


if __name__ == "__main__":
    main()
