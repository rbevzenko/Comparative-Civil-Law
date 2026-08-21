#!/usr/bin/env python3
"""Приклейка заголовка к номеру, оторванному переносом полосы.

    python scripts/join_number_to_heading.py --book <каталог> \
        [--pdf книга.pdf] [--number '^\\d{1,4}$'] [--min-size 13] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Зеркало join_heading_to_number.py: там номер стоит ПОД своим заголовком,
здесь — НАД ним, и чаще всего на предыдущей полосе.

У электронных изданий Dalloz в сборке calibre текст перевёрстан под экран, и
разрыв полосы попадает куда придётся. У Терре «Les biens» полоса 63
кончается строкой «32», а полоса 64 начинается словами «Catégories ◊
L'article 517 du Code civil énumère...». Номер единицы остаётся в одиночестве,
flow-паттерн его не узнаёт — ему нужен заголовок справа, — и пункт целиком
уходит в предыдущую карточку. Так теряется 42 номера из 957.

Строка-номер опознаётся по полному совпадению с `--number` и по кеглю не
ниже `--min-size`: номер набран кеглем тела или крупнее, а мелкая строка из
одних цифр — это знак сноски, и трогать её нельзя.

Заголовок берётся из следующей непустой строки — на этой же полосе или на
следующей, — и она приписывается к номеру через пробел. Сама строка при
этом со своего места убирается: иначе её текст попал бы в книгу дважды.

`--pdf` НУЖЕН ТАМ, ГДЕ НОМЕРА В МОДЕЛИ УЖЕ НЕТ. pipelib.strip_junk снимает
одинокое число из верхней и нижней полосы страницы — так вычищается
колонцифра. Проверка «число совпало с колонцифрой» его защищает, но только
пока колонцифра прочитана; у книги без колонцифры (`printed_page is None`)
правило срабатывает вслепую, и номер единицы, попавший на низ полосы,
исчезает вместе с ней. У Терре «Les biens» так пропало 42 номера из 957.

С `--pdf` номера ищутся в исходном файле, а не в модели: если одинокое
число в файле есть, а на этой полосе модели его нет — значит, его сняли, и
оно возвращается на место, к своему заголовку.
"""

import argparse
import json
import os
import re


def restore_from_pdf(pages, pdf_path, num_rx, min_size):
    """Вернуть номера, снятые вместе с колонцифрой, и приклеить к заголовку."""
    import sys
    sys.path.insert(0, "/root/.claude/skills/synced/complaw-corpus/scripts")
    import pdfplumber
    import pipelib as P

    by_page = {p["pdf_page"]: p for p in pages}
    order = [p["pdf_page"] for p in pages]
    pos = {n: i for i, n in enumerate(order)}
    restored = []

    with pdfplumber.open(pdf_path) as pdf:
        for n in order:
            page = pdf.pages[n - 1]
            lines = P.chars_to_lines(page.chars)
            page.flush_cache()
            for i, ln in enumerate(lines):
                s = ln["text"].strip()
                if (ln.get("size") or 0) < min_size or not num_rx.match(s):
                    continue
                model = by_page[n]["lines"]
                if any(l["text"].strip().startswith(s) for l in model):
                    continue      # номер на месте, снимать было нечего
                # заголовок — следующая непустая строка файла
                nxt = next((l["text"].strip() for l in lines[i + 1:] if l["text"].strip()), None)
                target = None
                if nxt:
                    target = next((l for l in model if l["text"].strip() == nxt), None)
                if target is None:
                    # заголовок на следующей полосе — берём её первую строку
                    k = pos[n] + 1
                    if k < len(order):
                        nxt_lines = by_page[order[k]]["lines"]
                        target = nxt_lines[0] if nxt_lines else None
                if target is None:
                    continue
                target["text"] = s + " " + target["text"].lstrip()
                restored.append((n, target["text"][:70]))

    print(f"возвращено номеров, снятых вместе с колонцифрой: {len(restored)}")
    for pg, t in restored[:15]:
        print(f"  полоса {pg}: {t}")
    return restored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", help="исходный PDF: искать номера в нём, а не в модели")
    ap.add_argument("--number", default=r"^\d{1,4}$")
    ap.add_argument("--min-size", type=float, default=13.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    num_rx = re.compile(a.number)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

    if a.pdf:
        restore_from_pdf(pages, a.pdf, num_rx, a.min_size)
        if a.dry_run:
            print("dry-run: файл не тронут")
            return
        with open(path, "w", encoding="utf-8") as f:
            for p in pages:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"записано: {path}")
        return

    # Плоский список ссылок на строки: перенос через полосу иначе не увидеть.
    flat = [(pi, li) for pi, p in enumerate(pages) for li in range(len(p["lines"]))]
    joined, drop = [], set()
    for k, (pi, li) in enumerate(flat):
        ln = pages[pi]["lines"][li]
        if (ln.get("size") or 0) < a.min_size:
            continue
        if not num_rx.match(ln["text"].strip()):
            continue
        # следующая непустая строка, где бы она ни лежала
        for pj, lj in flat[k + 1:k + 4]:
            nxt = pages[pj]["lines"][lj]
            if not nxt["text"].strip():
                continue
            if (pj, lj) in drop:
                break
            if (nxt.get("size") or 0) < a.min_size:
                break
            ln["text"] = ln["text"].strip() + " " + nxt["text"].strip()
            drop.add((pj, lj))
            joined.append((pages[pi]["pdf_page"], ln["text"][:70]))
            break

    for pi, p in enumerate(pages):
        p["lines"] = [l for li, l in enumerate(p["lines"]) if (pi, li) not in drop]

    print(f"склеено номеров с заголовком: {len(joined)}")
    for pg, t in joined[:15]:
        print(f"  полоса {pg}: {t}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
