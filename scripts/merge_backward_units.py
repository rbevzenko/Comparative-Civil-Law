#!/usr/bin/env python3
"""Склейка единиц, номер которых идёт назад.

    python scripts/merge_backward_units.py --book books/<id> [--dry-run]

Запускать после extract.py, до отчёта о качестве.

Для книг со сквозной нумерацией абзацев, где номер набран тем же кеглем и
тем же шрифтом, что и текст: «109. Ten eerste is dus …». Отличить такой
номер от начала перечисления («1. Definitie», «2. Belang») или от года в
начале перенесённой строки («2023. De wetgever heeft …») по виду нельзя —
ни кегль, ни шрифт, ни отступ не различаются. Различает их только одно:
сквозная нумерация идёт вперёд и назад не возвращается.

Карточка, номер которой не больше предыдущего принятого, единицей не
является: её текст приписывается к предыдущей карточке, а сама она
исчезает. Так «1. Definitie» возвращается в тот абзац, где и была
напечатана, вместо того чтобы завести в корпусе карточку-двойник.

Одного возрастания мало: год «2023» в начале перенесённой строки идёт
вперёд, и, приняв его, правило объявляет обратным ходом всю остальную книгу
— на живом прогоне от 1837 карточек оставалось 24. Поэтому шаг вперёд
ограничен сверху (`--max-step`): сквозная нумерация растёт на единицу, изредка
пропуская несколько номеров, но не прыгает на две тысячи.
"""

import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--max-step", type=int, default=20,
                    help="на сколько номер вправе обогнать предыдущий")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    def pos(card):
        page = card.get("page_start")
        box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
        return (page if page is not None else 10 ** 6, box["bbox"][1] if box else 0.0)

    ordered = sorted(cards, key=pos)
    kept, dropped, last = [], [], None
    for card in ordered:
        try:
            num = int(card["unit_number"])
        except (TypeError, ValueError):
            dropped.append(card)
            continue
        if last is not None and kept and not (last < num <= last + a.max_step):
            host = kept[-1]
            host["text"] = f"{host['text']}\n{card['unit_number']}. {card['text']}".strip()
            host["page_end"] = max(host.get("page_end") or 0, card.get("page_end") or 0) or host.get("page_end")
            dropped.append(card)
            continue
        kept.append(card)
        last = num

    print(f"карточек было: {len(cards)}, осталось: {len(kept)}, склеено назад: {len(dropped)}")
    for c in dropped[:8]:
        print(f"  {c['external_id']}: {c['text'][:56]!r}")
    if kept:
        nums = [int(c["unit_number"]) for c in kept]
        gaps = [x for x in range(nums[0], nums[-1] + 1) if x not in set(nums)]
        print(f"номера: {nums[0]}…{nums[-1]}, пропусков: {len(gaps)}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
