#!/usr/bin/env python3
"""Приведение адреса статьи DCFR/PEL к единому виду внутри книги.

    python scripts/normalize_article_address.py --book books/<id> [--dry-run]

Вёрстка тома 5–6 набирает один и тот же номер по-разному: «X. –1:101»,
«X.– 3:101», «X. – 2:102». Для человека это один адрес, для строки — три
разных, а адрес уходит и в external_id, и в постоянную ссылку на фрагмент.

Пробелы внутри номера снимаются, остальное не трогается: буква части,
римская цифра книги и разделитель остаются как напечатаны.
"""

import argparse
import json
import os
import re

# Римская цифра, необязательная буква части, тире, глава:статья.
ADDR = re.compile(r"\b([IVX]{1,4})\.\s*(?:([A-Z])\.\s*)?([–—‒-])\s*(\d{1,2})\s*:\s*(\d{3})\b")


def tidy(s):
    if not isinstance(s, str):
        return s
    return ADDR.sub(lambda m: f"{m.group(1)}.{(m.group(2)+'.') if m.group(2) else ''}"
                              f"{m.group(3)}{m.group(4)}:{m.group(5)}", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

    changed = 0
    for c in cards:
        before = (c.get("section"), c.get("address"), c.get("external_id"))
        for f in ("section", "address", "citation", "external_id", "id"):
            if f in c:
                c[f] = tidy(c[f])
        if (c.get("section"), c.get("address"), c.get("external_id")) != before:
            changed += 1

    ids = [c["external_id"] for c in cards]
    print(f"карточек: {len(cards)}, адрес приведён у {changed}")
    if len(set(ids)) != len(ids):
        raise SystemExit("после нормализации external_id перестали быть уникальными")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
