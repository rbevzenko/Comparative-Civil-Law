#!/usr/bin/env python3
"""Замена неотображённых глифов вида (cid:N) на настоящие знаки.

    python scripts/map_missing_glyphs.py --book <каталог> --map 2=N [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО остальных шагов.

Если во встроенном шрифте нет карты в Unicode, pdfplumber отдаёт знак как
«(cid:2)». У Bridge, The Law of Personal Property так набрана ПРОПИСНАЯ N:
в тексте стоит «Franklin v (cid:2)eate», «(cid:2)onetheless», а в
колонтитуле «REAL PROPERTY A(cid:2)D PERSO(cid:2)AL PROPERTY».

Подстановка не угадывается, а задаётся вручную: --map 2=N. Смотреть, какой
это знак, надо по окружению — код cid у каждого шрифта свой.

ЦЕЛЫЙ ШРИФТ РАЗБИРАЕТСЯ СМЕЩЕНИЕМ. У подмножества шрифта глифы нередко
идут в порядке ASCII, только со сдвигом: у Симлера, Les sûretés (Précis
Dalloz) cid 1 — пробел, cid 49 — «P», cid 66 — «a», то есть знак равен
cid + 31. Перечислять девяносто пять подстановок по одной бессмысленно,
поэтому есть `--offset НИЗ-ВЕРХ=СДВИГ`: cid из этого диапазона заменяется
на chr(cid + сдвиг).

Диапазон обязателен: за пределами ASCII порядок ломается. У того же Симлера
cid 207 — это «é», а не chr(238), и такие знаки задаются поштучно через
--map. Проверять надо по осмысленности: «Privilñge» вместо «Privilège»
означает, что для этого cid сдвиг не тот.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--map", action="append", default=[], metavar="CID=ЗНАК",
                    help="код cid и знак, которым его заменить; можно повторять")
    ap.add_argument("--offset", action="append", default=[], metavar="НИЗ-ВЕРХ=СДВИГ",
                    help="диапазон cid, который переводится в знак как chr(cid+сдвиг); "
                         "можно повторять")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    table = {}
    for item in a.offset:
        rng, _, shift = item.partition("=")
        lo, _, hi = rng.partition("-")
        for cid in range(int(lo), int(hi) + 1):
            table[f"(cid:{cid})"] = chr(cid + int(shift))
    # поштучные подстановки идут ПОСЛЕ диапазона и перекрывают его:
    # у акцентированных знаков порядок глифов сдвигу не подчиняется
    for item in a.map:
        cid, _, ch = item.partition("=")
        table[f"(cid:{cid.strip()})"] = ch
    if not table:
        ap.error("нужен хотя бы один --map или --offset")
    rx = re.compile("|".join(re.escape(k) for k in table))

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    hits = 0
    sample = None
    for pg in pages:
        for key in ("lines", "note_lines"):
            for ln in pg.get(key) or []:
                for field in (ln, *(ln.get("words") or [])):
                    t = field.get("text") or ""
                    if "(cid:" not in t:
                        continue
                    new = rx.sub(lambda m: table[m.group(0)], t)
                    if new != t:
                        if sample is None and field is ln:
                            sample = (t[:70], new[:70])
                        field["text"] = new
                        hits += 1

    print(f"замен: {hits}")
    if sample:
        print(f"  было:  {sample[0]!r}")
        print(f"  стало: {sample[1]!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
