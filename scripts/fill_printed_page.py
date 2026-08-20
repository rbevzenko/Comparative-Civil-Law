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

Флаг `--sequential` достраивает иначе: не по смещению от номера листа, а по
ПОРЯДКУ полос. Это для сканов разворотами (scripts/pages_spread.py), где на
одном листе две полосы книги и постоянного смещения нет вовсе. Между двумя
прочитанными номерами номера идут подряд — но достраивается только там, где
счёт сходится: если пропущенных полос больше, чем номеров между ними, в
скане не хватает листа, и выдуманный номер увёл бы адрес на чужую страницу.

Флаг `--drop-outliers` сначала стирает колонцифры, чьё смещение расходится
с преобладающим, и только потом достраивает. Это для случая, когда номер
прочитан НЕВЕРНО, а не отсутствует: у Duddington на двух полосах из 203
колонцифра слиплась с технической плашкой внизу («7711» вместо «71»), и
одна такая полоса делает разброс десятитысячным, после чего скрипт
отказывается достраивать все остальные.
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
    ap.add_argument("--sequential", action="store_true",
                    help="достраивать не по смещению от номера листа, а по порядку полос: "
                         "между двумя прочитанными номерами номера идут подряд")
    ap.add_argument("--drop-outliers", action="store_true",
                    help="сначала стереть колонцифры, чьё смещение расходится с "
                         "преобладающим, и только потом достраивать")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    known = [(p["pdf_page"], p["printed_page"]) for p in pages if p.get("printed_page")]
    if not known:
        print("Колонцифры нет ни на одной полосе — достраивать не от чего.")
        return

    if a.sequential:
        # Сначала снимаем одиночные ошибки чтения. У скана колонцифра
        # иногда читается с чужой строки: «137» на f139 там, где идёт 97.
        # Признак — смещение, не совпадающее НИ с предыдущим соседом, НИ со
        # следующим. Так отсеивается одиночный выброс, но не настоящий сдвиг
        # нумерации (вклейка, пропущенный оборот): тот держится многими
        # полосами подряд, и у первой же полосы после сдвига смещение
        # совпадает со следующей.
        marks = [(i, pg["printed_page"] - pg["pdf_page"])
                 for i, pg in enumerate(pages) if pg.get("printed_page")]
        dropped_lone = 0
        for k, (i, off) in enumerate(marks):
            prev_off = marks[k - 1][1] if k else None
            next_off = marks[k + 1][1] if k + 1 < len(marks) else None
            if prev_off is None and next_off is None:
                continue
            if off != prev_off and off != next_off:
                pages[i]["printed_page"] = None
                dropped_lone += 1
        if dropped_lone:
            print(f"снято одиночных ошибок чтения колонцифры: {dropped_lone}")

        anchors = [i for i, p in enumerate(pages) if p.get("printed_page")]
        filled = skipped = approx = 0
        if anchors:
            # Полосы ДО первого прочитанного номера и ПОСЛЕ последнего:
            # это шмуцтитул и первая полоса главы в начале тела и такие же в
            # конце. Считаем от края наружу.
            first, last = anchors[0], anchors[-1]
            for t in range(first - 1, -1, -1):
                pages[t]["printed_page"] = pages[first]["printed_page"] - (first - t)
                pages[t]["printed_page_filled"] = True
                filled += 1
            for t in range(last + 1, len(pages)):
                pages[t]["printed_page"] = pages[last]["printed_page"] + (t - last)
                pages[t]["printed_page_filled"] = True
                filled += 1
        for k in range(len(anchors) - 1):
            i, j = anchors[k], anchors[k + 1]
            lo, hi = pages[i]["printed_page"], pages[j]["printed_page"]
            if j - i < 2:
                continue
            # Достраиваем только там, где счёт сходится: между двумя
            # прочитанными номерами пропущенных полос ровно столько, сколько
            # номеров между ними. Иначе в скане не хватает листа, и
            # выдуманный номер увёл бы адрес на чужую страницу.
            if hi - lo != j - i:
                # Счёт не сошёлся: в скане не хватает полос (пустые обороты
                # перед началом главы цифровые переиздания часто не снимают).
                # Тогда считаем НАЗАД от следующего прочитанного номера:
                # полоса перед ним — это точно hi-1, а вот у самых ранних
                # полос прогона номер может оказаться на единицу больше
                # настоящего. Это шмуцтитулы и первые полосы глав, где текста
                # две строки, — лучше, чем оставить их без адреса вовсе.
                for t in range(j - 1, i, -1):
                    pages[t]["printed_page"] = hi - (j - t)
                    pages[t]["printed_page_filled"] = True
                    pages[t]["printed_page_approx"] = True
                    filled += 1
                    approx += 1
                continue
            for t in range(i + 1, j):
                pages[t]["printed_page"] = lo + (t - i)
                pages[t]["printed_page_filled"] = True
                filled += 1
        print(f"полос с колонцифрой: {len(known)} из {len(pages)}")
        print(f"достроено по порядку: {filled}, из них счётом назад: {approx}, "
              f"оставлено без номера: {skipped}")
        if a.dry_run:
            print("dry-run: файл не тронут")
            return
        with open(path, "w", encoding="utf-8") as f:
            for p in pages:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"Записано: {path}")
        return

    offsets = collections.Counter(pp - f for f, pp in known)
    main_off, main_n = offsets.most_common(1)[0]
    spread = max(offsets) - min(offsets)
    share = round(100 * main_n / len(known))
    print(f"полос с колонцифрой: {len(known)} из {len(pages)}")
    print(f"смещение: {main_off} у {share}% из них, разброс {spread}")

    if a.drop_outliers:
        dropped = []
        for p in pages:
            pp = p.get("printed_page")
            if pp and abs((pp - p["pdf_page"]) - main_off) > a.max_spread:
                dropped.append((p["pdf_page"], pp))
                p["printed_page"] = None
        if dropped:
            print(f"стёрто выбросов: {len(dropped)} — {dropped[:6]}")
        known = [(p["pdf_page"], p["printed_page"]) for p in pages if p.get("printed_page")]
        offsets = collections.Counter(pp - f for f, pp in known)
        main_off, main_n = offsets.most_common(1)[0]
        spread = max(offsets) - min(offsets)

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
