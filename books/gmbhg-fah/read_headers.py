#!/usr/bin/env python3
"""Колонтитул каждой полосы → work/headers.json.

    python read_headers.py --pdf <файл> --book <каталог> [--pages 54-2055]

Запускать после pages_digital.py: тот снимает колонтитул как шум (и правильно
делает — в тексте карточки ему нечего делать), но в самом колонтитуле этой
книги стоят ровно те две вещи, которых больше взять негде.

Первая — номер параграфа. Он есть на КАЖДОЙ полосе тела, тогда как в зашитом
оглавлении узлов с параграфом всего 126 на 2000 полос, и два узла экскурса
(«§10 IPRG», «§12 IPRG») указывают на одну и ту же полосу.

Вторая — автор комментария к этому параграфу. Издательство прямо предписывает
цитировать его: «Kurzform: A.Winkler/M.Winkler in FAH, GmbHG §1» (оборот
титула). Без автора ссылка на комментарий неполна.

Колонтитул печатается зеркально: на чётной типографской полосе «§16a Szöky»,
на нечётной «Hoffenscher-Summer §127». Поэтому автор берётся как остаток
строки после вычитания раздела, а не по позиции.
"""

import argparse
import json
import os
import re

EXKURS = [
    (re.compile(r"Exkurs:\s*§{0,2}\s*10\s*,\s*12\s*IPRG", re.I), "Exkurs IPRG"),
    (re.compile(r"Exkurs:\s*WiStR", re.I), "Exkurs WiStR"),
]
# Часть комментария написана сразу к нескольким параграфам, и колонтитул
# тогда перечисляет их все: «§§107, 112–114 Adensamer». Нумерация Rz у такого
# блока сквозная, поэтому раздел у него один и составной; разобрать его надо
# ДО одиночного «§ N», иначе §107 заберёт блок себе, а «112–114» уедет в
# фамилию автора.
MULTI = re.compile(r"§§\s*(\d[\d\s]*[a-z]?)\s*,\s*(\d[\d\s]*[a-z]?)\s*[–—-]\s*(\d[\d\s]*[a-z]?)")
RANGE = re.compile(r"§§\s*(\d[\d\s]*[a-z]?)\s*[–—-]\s*(\d[\d\s]*[a-z]?)")
# pypdf кое-где вставляет пробел внутрь номера: «§1 6a» — это §16a.
SECTION = re.compile(r"§\s*(\d[\d\s]{0,4})\s*([a-z])?(?![\w])")


def tidy(part):
    return re.sub(r"\s+", "", part)


def parse(line):
    s = " ".join(line.split())
    for rx, name in EXKURS:
        m = rx.search(s)
        if m:
            return name, (s[:m.start()] + s[m.end():]).strip(" .,")
    m = MULTI.search(s)
    if m:
        num = f"{tidy(m.group(1))}, {tidy(m.group(2))}–{tidy(m.group(3))}"
        return num, (s[:m.start()] + s[m.end():]).strip(" .,")
    m = RANGE.search(s)
    if m:
        num = f"{tidy(m.group(1))}–{tidy(m.group(2))}"
        return num, (s[:m.start()] + s[m.end():]).strip(" .,")
    m = SECTION.search(s)
    if not m:
        return None, None
    num = tidy(m.group(1)) + (m.group(2) or "")
    return num, (s[:m.start()] + s[m.end():]).strip(" .,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--pages", default="54-2055")
    a = ap.parse_args()

    from pypdf import PdfReader

    lo, hi = (int(x) for x in a.pages.split("-"))
    reader = PdfReader(a.pdf)
    out, blank = {}, 0
    for pno in range(lo, hi + 1):
        text = reader.pages[pno - 1].extract_text() or ""
        first = next((l for l in text.splitlines() if l.strip()), "")
        sec, author = parse(first)
        if sec is None:
            blank += 1
            continue
        out[str(pno)] = {"section": sec, "author": author, "raw": first.strip()[:80]}

    by_section = {}
    for v in out.values():
        by_section.setdefault(v["section"], {}).setdefault(v["author"], 0)
        by_section[v["section"]][v["author"]] += 1
    print(f"полос осмотрено: {hi - lo + 1}, колонтитул прочитан: {len(out)}, без раздела: {blank}")
    print(f"разделов: {len(by_section)}")
    mixed = {s: v for s, v in by_section.items() if len(v) > 1}
    if mixed:
        print(f"разделов с разночтением автора: {len(mixed)} — берётся частотный")
        for s, v in list(mixed.items())[:6]:
            print(f"  §{s}: {v}")

    path = os.path.join(a.book, "work", "headers.json")
    json.dump({"pages": out,
               "authors": {s: max(v, key=v.get) for s, v in by_section.items()}},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
