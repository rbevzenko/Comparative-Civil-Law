#!/usr/bin/env python3
"""Снятие полос, снятых сканером дважды.

    python scripts/drop_duplicate_pages.py --book <каталог> [--window 12] [--head 200] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Сканер иногда снимает разворот дважды: у Hanbury & Martin, Modern Equity
полосы f131 и f133 — это одна и та же страница 33, а f132 и f136 — одна и та
же 32. В корпусе это даёт ДУБЛИ АДРЕСА: один и тот же абзац «1-042»
приходит двумя карточками.

Сравниваются первые `--head` знаков текста полосы, и только с соседями в
пределах `--window` полос: одинаковое начало у двух полос из разных концов
книги — это совпадение вёрстки (шмуцтитул, пустая полоса), а не повтор
скана. Из пары остаётся ПОЗДНЯЯ полоса: у Hanbury повтор идёт перед
оригиналом, и порядок абзацев после снятия ранней восстанавливается.
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
    ap.add_argument("--window", type=int, default=12)
    ap.add_argument("--head", type=int, default=200)
    ap.add_argument("--keep", choices=["first", "last"], default="last")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    def key(pg):
        t = " ".join((l.get("text") or "") for l in (pg.get("lines") or []))
        t = re.sub(r"\s+", " ", t).strip().lower()
        return t[:a.head] if len(t) >= 40 else None

    keys = [key(p) for p in pages]
    drop = set()
    for i, k in enumerate(keys):
        if k is None or i in drop:
            continue
        for j in range(i + 1, min(i + 1 + a.window, len(pages))):
            if keys[j] != k:
                continue
            drop.add(i if a.keep == "last" else j)
            break

    sample = [(pages[i]["pdf_page"], (keys[i] or "")[:50]) for i in sorted(drop)[:5]]
    print(f"снято повторов скана: {len(drop)} из {len(pages)} полос")
    for pno, head in sample:
        print(f"  f{pno}: {head!r}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for i, pg in enumerate(pages):
            if i in drop:
                pg["lines"] = []
                pg["duplicate_scan"] = True
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
