#!/usr/bin/env python3
"""Обрезка карточки по заголовку, за которым начинается чужой текст.

    python scripts/trim_after.py --book books/<id> --pattern '^CHAPITRE 3' [--dry-run]

Запускать после extract.py, до отчёта о качестве.

Последняя единица раздела дотягивается до следующего заголовка, а если
следующий заголовок пайплайну не единица — то и дальше. У бельгийских
парламентских документов за постатейными мотивами к статьям Кодекса идут
мотивы к техническим статьям самого законопроекта («Art. 3. Par cet article,
les articles 2011 à 2043octies … sont abrogés»), и весь этот хвост оседает в
карточке последней статьи Кодекса.

Скрипт режет текст карточки по первой строке, отвечающей паттерну. Паттерн
проверяется по НАЧАЛУ строки (флаг re.M), поэтому «CHAPITRE 3» в середине
фразы карточку не тронет.
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
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--min-keep", type=int, default=40,
                    help="сколько знаков карточка обязана сохранить, иначе не режем")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rx = re.compile(a.pattern, re.M)
    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    cut, dropped, skipped = 0, 0, []
    for c in cards:
        m = rx.search(c["text"])
        if not m:
            continue
        if m.start() < a.min_keep:
            skipped.append(c["external_id"])
            continue
        dropped += len(c["text"]) - m.start()
        print(f"  {c['external_id']}: снято {len(c['text']) - m.start()} знаков "
              f"начиная с {c['text'][m.start():m.start() + 40]!r}")
        c["text"] = c["text"][:m.start()].rstrip()
        cut += 1

    print(f"карточек обрезано: {cut}, снято знаков: {dropped}")
    if skipped:
        print(f"не тронуты (заголовок в самом начале): {len(skipped)} — {skipped[:5]}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
