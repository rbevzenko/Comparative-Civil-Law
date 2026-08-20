#!/usr/bin/env python3
"""Иерархия карточки — из КОЛОНТИТУЛА полосы, а не из заголовков в тексте.

    python scripts/hierarchy_from_running_head.py --book <каталог> \
        --pdf <файл> --band 0.06 [--size-min 10.8] [--size-max 12] \
        [--min-chars 8] [--dry-run]

Запускать ПОСЛЕ extract.py.

Зачем. `hierarchy_from_headings.py` ищет заголовки в ТЕЛЕ полосы и годится
там, где они набраны отличимо. У сборников это не всегда так: у Оксфордского
справочника (распечатка из Oxford Handbooks Online) заголовок главы стоит
только в колонтитуле, а сам колонтитул снимается при разборе полосы — иначе
он попал бы в каждую карточку.

Здесь колонтитул читается ПРЯМО ИЗ PDF, по полосе и кеглю, и кладётся в
`hierarchy` карточки. Для сборника из полусотни очерков это разница между
«фрагмент неизвестно откуда» и «фрагмент из такой-то главы».

Полоса `--band` — доля высоты страницы сверху. Кегль ограничивается, чтобы
не принять за колонтитул первую строку текста.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--band", type=float, default=0.06)
    ap.add_argument("--size-min", type=float)
    ap.add_argument("--size-max", type=float)
    ap.add_argument("--min-chars", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pdfplumber

    heads = {}
    with pdfplumber.open(a.pdf) as pdf:
        for i, pg in enumerate(pdf.pages, 1):
            hi = pg.height * a.band
            ws = [w for w in pg.extract_words(extra_attrs=["size"]) if w["top"] <= hi]
            if a.size_min is not None:
                ws = [w for w in ws if w["size"] >= a.size_min]
            if a.size_max is not None:
                ws = [w for w in ws if w["size"] <= a.size_max]
            if not ws:
                continue
            top = min(w["top"] for w in ws)
            line = [w for w in ws if abs(w["top"] - top) < 2.0]
            text = " ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"])).strip()
            # Колонцифра сама по себе колонтитулом не является.
            text = re.sub(r"^\d{1,4}\s+|\s+\d{1,4}$", "", text).strip()
            if len(text) >= a.min_chars:
                heads[i] = text

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    seen, missed = collections.Counter(), 0
    for c in cards:
        h = heads.get(c.get("page_start"))
        if not h:
            missed += 1
            continue
        c["hierarchy"] = [h]
        seen[h] += 1

    print(f"колонтитулов прочитано: {len(set(heads.values()))} разных на {len(heads)} полосах")
    print(f"карточек с иерархией: {len(cards) - missed} из {len(cards)}")
    for h, n in seen.most_common(5):
        print(f"  {n:5d}  {h[:70]}")
    if missed:
        print(f"без колонтитула: {missed}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for c in cards:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
