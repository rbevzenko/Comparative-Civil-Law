#!/usr/bin/env python3
"""Взять номер раздела из иерархии и вписать его в адрес карточки.

    python scripts/section_from_hierarchy.py --book <каталог> \
        --pattern '^Part\\s+(\\w+)' --words --template 'para. {section}-{number}' \
        [--level 0] [--dry-run]

Запускать ПОСЛЕ extract.py (и hierarchy_from_headings.py, если иерархия
строится отдельно), ДО qa_report.py.

Зачем. В сборниках и коллективных исследованиях счёт абзацев идёт заново в
каждой части: у von Bar/Drobnig, Interaction of Contract Law and Tort and
Property Law in Europe, номера 1–427 в Части первой начинаются сызнова в
Части второй. Адрес «para. 14» перестаёт быть адресом: он указывает на
пять разных мест, а `external_id` внутри выгрузки обязан быть уникальным —
иначе приёмник отвергает файл целиком.

Номер части печатается в колонтитуле, но колонтитул снимается ещё при
разборе полосы: его строка нужна была, чтобы прочитать колонцифру. Зато
часть остаётся в ИЕРАРХИИ карточки, и брать её оттуда надёжнее — иерархия
уже сверена с заголовками.

`--words` переводит числительные словами в цифры (Part One → 1). Без него
в адрес идёт то, что поймал шаблон, как есть.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import collections
import json
import re

WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pattern", required=True,
                    help="шаблон по узлу иерархии; группа 1 — номер раздела")
    ap.add_argument("--level", type=int, default=0, help="глубина узла, с нуля")
    ap.add_argument("--words", action="store_true",
                    help="числительные словами и римские цифры перевести в арабские")
    ap.add_argument("--template", default="{unit} {section}-{number}",
                    help="шаблон адреса; поля {unit} {section} {number}")
    ap.add_argument("--split-restarts", action="store_true",
                    help="счёт внутри раздела начинается заново — считать это "
                         "новым подразделом (4, 4.2, 4.3…)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rx = re.compile(a.pattern)
    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    seen, missed, restarts = collections.Counter(), 0, 0
    seq = {}
    for c in cards:
        nodes = c.get("hierarchy") or []
        node = nodes[a.level] if len(nodes) > a.level else None
        m = rx.search(node) if node else None
        if not m:
            missed += 1
            continue
        key = m.group(1)
        if a.words:
            key = WORDS.get(key.strip().lower(), key)
        num = c.get("number")
        if a.split_restarts:
            # Внутри одного раздела номера обязаны возрастать. Пошли по
            # второму кругу — значит, рядом идёт ВТОРАЯ нумерация: у von Bar
            # Часть четвёртая это анкеты, и вопросы каждого тура нумеруются
            # с единицы. Подраздел получает номер после точки: 4, 4.2, 4.3.
            #
            # Ряды именно ЧЕРЕДУЮТСЯ, а не сменяют друг друга: после чужого
            # прогона книга возвращается к основному счёту (…427, потом
            # 116…155, потом снова 428). Поэтому карточка кладётся в тот
            # ряд, который она ПРОДОЛЖАЕТ, — в первый, чей последний номер
            # меньше. Простая метка «сменился ряд» рвала основной счёт на
            # части: у Части первой получался пропуск в 311 номеров.
            runs = seq.setdefault(key, [])
            if not isinstance(num, int):
                idx = 0 if runs else None
                if idx is None:
                    runs.append(0)
                    idx = 0
            else:
                idx = next((i for i, last in enumerate(runs) if num > last), None)
                if idx is None:
                    runs.append(num)
                    idx = len(runs) - 1
                    if idx:
                        restarts += 1
                else:
                    runs[idx] = num
            if idx:
                key = f"{key}.{idx + 1}"
        c["section"] = key
        c["address"] = a.template.format(unit=(c.get("unit") or "").rstrip("."),
                                         section=key, number=c.get("number"))
        base = c["external_id"].rsplit(":", 1)[0]
        c["external_id"] = f"{base}:{key}/{c.get('number')}"
        seen[str(key)] += 1

    dup = collections.Counter(c["external_id"] for c in cards)
    dups = [k for k, v in dup.items() if v > 1]

    print(f"карточек: {len(cards)}, разделов: {len(seen)}")
    for k in sorted(seen, key=lambda s: (len(s), s)):
        print(f"  раздел {k}: {seen[k]}")
    if missed:
        print(f"без раздела (узел не подошёл под шаблон): {missed}")
    if restarts:
        print(f"повторных прогонов счёта внутри разделов: {restarts}")
    print(f"дублей external_id после правки: {len(dups)}")
    for d in dups[:5]:
        print(f"  {d}")
    if cards:
        print(f"  пример: {cards[0]['external_id']} → {cards[0]['address']}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for c in cards:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
