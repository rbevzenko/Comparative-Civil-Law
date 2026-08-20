#!/usr/bin/env python3
"""Приклейка заголовка абзаца к строке с его номером.

    python scripts/join_heading_to_number.py --book <каталог> \
        --number '^\\d{1,2}-\\d{3}$' [--min-size 11] [--skip '^Volume \\d'] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

У выгрузок Westlaw/ProView (Chitty on Contracts, Goff & Jones) номер абзаца
стоит ОТДЕЛЬНОЙ строкой, а над ним — свой заголовок:

    No Consideration Required
    1-136
    Generally speaking, as will be seen later in detail, …

Единица начинается со строки с номером, поэтому заголовок достаётся хвосту
ПРЕДЫДУЩЕЙ карточки — то есть уходит в чужой абзац, к которому не относится.
Скрипт сращивает его со своей строкой в «1-136 No Consideration Required»,
и дальше обычный flow-паттерн отрезает номер, а заголовок открывает текст
карточки, как в книге.

Заголовок опознаётся по кеглю (--min-size): он набран крупнее основного
текста, тем же кеглем, что и номер. Строки колонтитула выгрузки («Volume 1 -
General Principles», «Chapter 1 - Introductory») набраны так же и от
заголовка по виду не отличаются — их перечисляют в --skip.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--number", required=True, help="строка-номер единицы, полное совпадение")
    ap.add_argument("--min-size", type=float, default=11.0,
                    help="минимальный кегль строки, которая может быть заголовком")
    ap.add_argument("--max-lines", type=int, default=1,
                    help="сколько строк подряд может занимать заголовок")
    ap.add_argument("--head-start", default=None,
                    help="с чего заголовок вправе начинаться; всё выше первой такой строки отбрасывается")
    ap.add_argument("--skip", action="append", default=[],
                    help="строка, которая заголовком не бывает (колонтитул выгрузки)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    num_rx = re.compile(a.number)
    skips = [re.compile(rx) for rx in a.skip]
    head_rx = re.compile(a.head_start) if a.head_start else None
    path = os.path.join(a.book, "work", "pages.jsonl")
    joined = bare = 0
    sample = []
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in fh:
            pg = json.loads(row)
            lines = pg.get("lines") or []
            keep, drop = [], set()
            for i, ln in enumerate(lines):
                if not num_rx.match(ln["text"].strip()):
                    continue
                # Заголовок бывает и в две строки («Contracts for the Sale of /
                # a Person's Property»). Взять только последнюю — значит
                # оставить в адресе обрывок, начинающийся со строчной.
                head_lines = []
                j = i - 1
                while j >= 0 and len(head_lines) < a.max_lines:
                    cand = lines[j]
                    text = cand["text"].strip()
                    if ((cand.get("size") or 0) < a.min_size or not text
                            or num_rx.match(text) or any(rx.match(text) for rx in skips)):
                        break
                    head_lines.append((j, cand))
                    j -= 1
                head_lines.reverse()
                # Хвост колонтитула выгрузки: строка «Sub-section (x) - The
                # Unfair Terms in Consumer Contracts Regulations» снимается
                # как мусор, а перенесённый на следующую строку «1999»
                # остаётся сиротой того же кегля — и уходит в заголовок
                # абзаца впереди его собственного текста. Настоящий заголовок
                # начинается с прописной, поэтому всё, что стоит выше первой
                # такой строки, отбрасывается.
                if head_rx is not None:
                    while head_lines and not head_rx.match(head_lines[0][1]["text"].strip()):
                        head_lines.pop(0)
                if not head_lines:
                    bare += 1
                    continue
                head = " ".join(h["text"].strip() for _, h in head_lines)
                if len(sample) < 6:
                    sample.append((pg["pdf_page"], head[:60], ln["text"].strip()))
                ln["text"] = f"{ln['text'].strip()} {head}"
                for idx, h in head_lines:
                    ln["words"] = list(ln.get("words") or []) + list(h.get("words") or [])
                    ln["top"] = min(ln["top"], h["top"])
                    ln["x0"] = min(ln["x0"], h["x0"])
                    ln["x1"] = max(ln["x1"], h["x1"])
                    drop.add(idx)
                joined += 1
            keep = [ln for i, ln in enumerate(lines) if i not in drop]
            pg["lines"] = keep
            out.append(pg)

    print(f"номеров с приклеенным заголовком: {joined}, без заголовка: {bare}")
    for pno, head, num in sample:
        print(f"  f{pno}: {num!r} + {head!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in out:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
