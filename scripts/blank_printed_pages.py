#!/usr/bin/env python3
"""Снять колонцифру там, где она не колонцифра.

    python scripts/blank_printed_pages.py --book books/<id> [--dry-run]

Запускать сразу ПОСЛЕ pages_digital.py.

ЗАЧЕМ. У электронных изданий Dalloz внизу каждой полосы стоит число, и
разбор честно принимает его за типографскую страницу. Но это нумерация
ФАЙЛА: у Терре по обязательствам 3095 полос, из них 904 заняты аппаратом,
а в бумажном издании страниц около 1900. Сохранить такое число как
`printed_page` значит выдать пользователю ссылку на страницу, которой в
книге нет.

Убрать число из профиля нельзя: пока оно читается, строка с ним снимается
с полосы и не попадает в текст карточки. Поэтому читаем — и обнуляем.

Французская книга цитируется по номеру пункта (n°), так что без страницы
адрес не теряет ничего: в карточке остаётся полоса файла, и по ней виден
разворот исходника.
"""

import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    had = sum(1 for p in pages if p.get("printed_page") is not None)
    for p in pages:
        p["printed_page"] = None
    print(f"полос: {len(pages)}, колонцифра снята у {had}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
