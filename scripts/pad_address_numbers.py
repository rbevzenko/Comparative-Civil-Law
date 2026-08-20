#!/usr/bin/env python3
"""Восстановление ведущих нулей в номере единицы.

    python scripts/pad_address_numbers.py --book books/<id> --width 3 [--dry-run]

Запускать после extract.py, до отчёта о качестве.

extract.py хранит номер единицы целым числом: непрерывность ряда и починка
опечаток считаются по числу, и иначе их не посчитать. Но книга, у которой
номер набран с ведущими нулями, и цитируется с ними: у Snell's Equity это
«para.3-031», а не «para.3-31», и ссылка без нулей в английской практике
просто не ищется.

Скрипт дополняет номер нулями в тех полях, которые видит человек: адрес,
цитата и unit_number. В адресе и цитате правится ПОСЛЕДНЕЕ вхождение числа:
у составного адреса первым числом стоит раздел, и его дополнять нечем. Целое `number` и `external_id` не трогаются — по ним
считается ряд и по ним идёт идемпотентность загрузки.
"""

import argparse
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--width", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    changed = 0
    sample = []
    for c in cards:
        num = c.get("number")
        if not isinstance(num, int):
            continue
        bare, padded = str(num), str(num).zfill(a.width)
        if bare == padded:
            continue
        # Заменяется ПОСЛЕДНЕЕ вхождение: у составного адреса «para. 1-1»
        # первым числом стоит раздел, и слепая замена делает из него
        # «para. 001-001». Номер единицы в адресе идёт последним.
        rx = re.compile(r"(?<!\d)%s(?!\d)" % re.escape(bare))
        before = c.get("address")
        for field in ("address", "citation"):
            if not c.get(field):
                continue
            hits = list(rx.finditer(c[field]))
            if not hits:
                continue
            last = hits[-1]
            c[field] = c[field][:last.start()] + padded + c[field][last.end():]
        c["unit_number"] = padded
        changed += 1
        if len(sample) < 5:
            sample.append((before, c.get("address")))

    print(f"карточек с дополненным номером: {changed} из {len(cards)}")
    for before, after in sample:
        print(f"  {before!r} → {after!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
