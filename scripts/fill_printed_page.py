#!/usr/bin/env python3
"""Достройка колонцифры на полосах, где её не напечатали.

    python scripts/fill_printed_page.py --book <каталог> [--max-spread 0] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Колонцифру не печатают на первой полосе главы, на шмуцтитуле и на полосе,
целиком занятой таблицей. У Virgo, Principles of the Law of Restitution
таких полос 45 из 741, и карточки с них приходят без адреса вовсе, потому
что адресом у этой книги служит именно страница.

Смещение между номером полосы файла и номером страницы книги проверяется
по тем полосам, где колонцифра есть. Если оно ОДНО на всю книгу (разброс не
больше --max-spread), недостающие номера достраиваются по нему. Если
смещение гуляет — вклейки, вкладки, несколько нумераций, — скрипт ничего не
делает и говорит об этом: выдуманная страница хуже отсутствующей.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import collections
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--max-spread", type=int, default=0,
                    help="на сколько смещение вправе гулять, чтобы считаться постоянным")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    known = [(p["pdf_page"], p["printed_page"]) for p in pages if p.get("printed_page")]
    if not known:
        print("Колонцифры нет ни на одной полосе — достраивать не от чего.")
        return

    offsets = collections.Counter(pp - f for f, pp in known)
    main_off, main_n = offsets.most_common(1)[0]
    spread = max(offsets) - min(offsets)
    share = round(100 * main_n / len(known))
    print(f"полос с колонцифрой: {len(known)} из {len(pages)}")
    print(f"смещение: {main_off} у {share}% из них, разброс {spread}")

    if spread > a.max_spread:
        print("Смещение непостоянное — ничего не достраиваю: выдуманная страница "
              "хуже отсутствующей.")
        return

    filled = 0
    for p in pages:
        if not p.get("printed_page"):
            p["printed_page"] = p["pdf_page"] + main_off
            p["printed_page_filled"] = True
            filled += 1
    print(f"достроено: {filled}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
