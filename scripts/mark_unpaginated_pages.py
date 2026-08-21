#!/usr/bin/env python3
"""Полосы без колонцифры получают честный адрес «frg. N», а не чужой номер.

    python scripts/mark_unpaginated_pages.py --book books/<id> [--dry-run]

Запускать ПОСЛЕ extract.py в книгах с единицей `mode: page`.

Что чинится. Когда колонцифра на полосе не прочитана, extract.py
подставляет номер полосы ФАЙЛА. Это тихая подмена двух нумераций: у
сборника отчётов номер файла 22 сталкивается с настоящей печатной
страницей 22 (она лежит на полосе 35), и приёмник отвергает весь файл —
«external_id не уникальны». Хуже отказа то, что адрес при этом врёт:
карточка обещает страницу книги, а несёт номер полосы файла.

Колонцифры нет не по недосмотру разбора: на первой полосе раздела
колонтитул не печатают, а живёт она именно в нём.

Такие карточки переводятся в семейство `frg.` — «фрагмент файла». Адрес
«frg. 21» честно говорит: это двадцать первая полоса файла, печатной
страницы у неё не прочитано. Тот же приём уже применён в корпусе к
электронным книгам без типографской пагинации.
"""

import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

    touched = 0
    for c in cards:
        if c.get("unit_type") != "p." or c.get("printed_page_start") is not None:
            continue
        n = c.get("page_start")
        book_id = c["book_id"]
        c["unit"] = c["unit_type"] = "frg."
        c["unit_number"] = str(n)
        c["address"] = f"frg. {n}"
        c["external_id"] = f"{book_id}:frg:{n}"
        c["id"] = f"{book_id}-frg{n}"
        # Цитата собрана по старому адресу — пересобирать её нечем, поэтому
        # правится хвост: адрес в ней стоит последним по шаблону профиля.
        old = f"p. {n}"
        if c.get("citation", "").endswith(old):
            c["citation"] = c["citation"][: -len(old)] + c["address"]
        touched += 1

    ids = [c["external_id"] for c in cards]
    print(f"карточек {len(cards)}, без колонцифры {touched}, уникальных ключей {len(set(ids))}")
    if len(set(ids)) != len(ids):
        raise SystemExit("ключи всё ещё не уникальны — смотреть глазами, что за карточки")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
