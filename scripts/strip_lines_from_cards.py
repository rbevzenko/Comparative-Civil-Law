#!/usr/bin/env python3
"""Убрать из готовых карточек строки, которые оказались мусором.

    python scripts/strip_lines_from_cards.py books/de-* --pattern '^https?://\\S+ \\d+/\\d+$' [--dry-run]

Нужен там, где мусорная строка обнаружилась ПОСЛЕ нарезки и перенарезать
ради неё сотню книг дороже, чем поправить текст на месте. Приёмник обновляет
карточку по `external_id`, так что перезаливка правит строки, а не удваивает
их.

Правило применяется к строкам целиком: `--pattern` сверяется с каждой
строкой текста карточки, а не с текстом целиком. Так надёжнее: подвал
страницы всегда стоит отдельной строкой, а те же знаки внутри абзаца трогать
нельзя.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+")
    ap.add_argument("--pattern", action="append", default=[],
                    help="строка целиком, совпавшая с образцом, выбрасывается")
    ap.add_argument("--replace", action="append", default=[],
                    help="кусок строки, совпавший с образцом, вырезается: подвал\n"
                         "полосы бывает приклеен к концу последней строки текста")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.pattern and not a.replace:
        sys.exit("нужен хотя бы один --pattern или --replace")
    rx = [re.compile(p) for p in a.pattern]
    sub = [re.compile(p) for p in a.replace]
    total_cards = total_lines = 0
    for book in a.books:
        path = os.path.join(book, "output", "cards.jsonl")
        if not os.path.exists(path):
            continue
        cards = P.read_jsonl(path)
        n = k = 0
        for c in cards:
            lines = c["text"].split("\n")
            keep = [l for l in lines if not any(r.search(l.strip()) for r in rx)]
            if sub:
                cleaned = []
                for l in keep:
                    for r in sub:
                        l = r.sub("", l)
                    cleaned.append(l.rstrip())
                if cleaned != keep:
                    k += sum(1 for x, y in zip(cleaned, keep) if x != y)
                    keep = cleaned
            if keep != lines:
                k += len(lines) - len(keep)
                c["text"] = "\n".join(keep)
                n += 1
        if n and not a.dry_run:
            P.write_jsonl(path, cards)
        if n:
            print(f"  {os.path.basename(book)}: карточек {n}, строк снято {k}")
        total_cards += n
        total_lines += k
    print(f"всего: карточек {total_cards}, строк снято {total_lines}")


if __name__ == "__main__":
    main()
