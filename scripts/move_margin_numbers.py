#!/usr/bin/env python3
"""Перенос составного маргинального номера с правого поля в начало строки.

    python scripts/move_margin_numbers.py --book <каталог> --pattern '^\\d{1,2}-\\d{3}$' \
        --min-x 380 [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Штатный режим `margin` в extract.py берёт с поля только ГОЛОЕ число:
pull_margin_tokens проверяет токен через `re.fullmatch(r"\\d{1,4}", s)`.
Составной номер («3-031» у Snell's Equity, где 3 — глава, а 031 — абзац
внутри главы) под это не подходит, и режим margin теряет все адреса.

Разворот у таких книг устроен так, что номер стоит на ВНЕШНЕМ поле и меняет
сторону: на одной странице он и так первое слово строки, и flow-режим читает
его сам, а на другой — последнее слово, за правым краем полосы набора.
Скрипт переносит второй случай в начало строки, и дальше обе стороны
разбираются одним flow-паттерном.

Переносится только ПОСЛЕДНЕЕ слово строки и только если оно стоит правее
--min-x. Порог важен: тем же паттерном набраны перекрёстные ссылки в тексте
(«see para. 3-042») и строки постраничного оглавления главы с отточием, но
они лежат внутри полосы набора, а поле начинается за её правым краем.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pattern", required=True, help="полное совпадение со словом на поле")
    ap.add_argument("--min-x", type=float, required=True, help="левая граница поля в пунктах")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rx = re.compile(a.pattern)
    path = os.path.join(a.book, "work", "pages.jsonl")
    moved = already = 0
    sample = []
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in fh:
            pg = json.loads(row)
            for ln in pg.get("lines") or []:
                words = ln.get("words") or []
                if not words:
                    continue
                if rx.match(words[0]["text"].strip()):
                    already += 1
                    continue
                last = words[-1]
                if not rx.match(last["text"].strip()) or last["x0"] < a.min_x:
                    continue
                rest = words[:-1]
                if not rest:
                    continue
                ln["words"] = [last] + rest
                before = ln["text"]
                ln["text"] = (last["text"] + " " + " ".join(w["text"] for w in rest)).strip()
                ln["x0"] = min(w["x0"] for w in ln["words"])
                ln["x1"] = max(w["x1"] for w in ln["words"])
                moved += 1
                if len(sample) < 5:
                    sample.append((pg["pdf_page"], before[-60:], ln["text"][:70]))
            out.append(pg)

    print(f"перенесено с правого поля: {moved}")
    print(f"уже стояло первым словом (левое поле): {already}")
    for pgno, before, after in sample:
        print(f"  f{pgno}: …{before!r}\n      → {after!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in out:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
