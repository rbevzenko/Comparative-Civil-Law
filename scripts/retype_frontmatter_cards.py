#!/usr/bin/env python3
"""Вступление параграфа — не Randnummer, и в ряд номеров его ставить нельзя.

    python scripts/retype_frontmatter_cards.py books/de-* [--dry-run]

Первая карточка параграфа несёт то, что стоит ДО первого номера: Schrifttum,
систематический обзор, текст самой нормы. Номера у неё нет, и разборщик
ставит ей ноль. Отчёт о качестве считает ряды по паре (тип единицы, раздел),
и этот ноль попадает в ряд Randnummern: у § 280 Staudinger в файле напечатаны
только Rn. 100–141, и вместе с нулём это выглядит дырой в девяносто девять
номеров, хотя в файле просто нет этих страниц.

Здесь такие карточки получают собственный тип «Vorspann». Ряд Randnummern
становится честным, а вступление не теряется и остаётся на своём месте:
адрес и external_id не меняются.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+")
    ap.add_argument("--type", default="Vorspann")
    ap.add_argument("--sectionless-type",
                    help="тип для карточек без раздела. Выбрасывать их нельзя: у Jaeger\n"
                         "Band 9 это четверть текста тома. Но и в ряду Randnummern им не\n"
                         "место — «Rdn. 2002» среди номеров до 432 роняет непрерывность\n"
                         "тома с 0.95 до 0.56. Свой тип выводит их из ряда, сохранив текст")
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
            if c.get("number") == 0 and c.get("unit_type") != a.type:
                c["unit"] = c["unit_type"] = a.type
                n += 1
        loose = 0
        if a.sectionless_type:
            for c in cards:
                if not c.get("section") and c.get("number") is not None:
                    # Номер у такой карточки не просто чужой, а выдуманный:
                    # в предисловии тома за Randnummer принято случайное число
                    # («2019» при ряде до 564). Оставить его — значит держать в
                    # корпусе несуществующий адрес и ронять непрерывность тома.
                    # Поэтому номер снимается совсем, а текст остаётся.
                    c["unit"] = c["unit_type"] = a.sectionless_type
                    c["number"] = None
                    c["unit_number"] = ""
                    c["address"] = a.sectionless_type
                    loose += 1
        if (n or loose) and not a.dry_run:
            P.write_jsonl(path, cards)
        if loose:
            print(f"  {os.path.basename(book)}: без раздела перетипировано {loose}")
        if n:
            print(f"  {os.path.basename(book)}: {n}")
        total += n
    print(f"вступлений перетипировано: {total}")


if __name__ == "__main__":
    main()
