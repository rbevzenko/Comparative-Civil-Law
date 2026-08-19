#!/usr/bin/env python3
"""Врезки мелким кеглем — обратно в тело полосы.

    python restore_body_boxes.py --book <каталог> [--dry-run]

Запускать сразу после pages_digital.py и ДО fix_footnote_markers.py.

Профиль этой книги отделяет сноски по кеглю и низу полосы, и полоса взята
низко — 0.45: аппарат здесь тяжёлый, блок сносок начинается порой на 0.46
высоты, а при полосе 0.75 в теле осталось бы 892 строки сносок.

Цена низкой полосы известна заранее: тем же мелким кеглем в этой книге
набраны две врезки, и они не аппарат, а текст —

    f70  «Sachnormverweisung – Gesamtverweisung» — подзаголовок-ключ под
         заголовком § 7;
    f244 «ÜBERSICHT» — план CISG по частям, содержательная часть Rz 19/5.

Признак, по которому они отличаются от сносок, не в кегле и не в положении,
а в том, что в блоке нет НИ ОДНОГО номера сноски и первая строка не
продолжает фразу с предыдущей полосы (начинается с прописной). Настоящий
блок сносок без номеров бывает только один — перенос сноски на следующую
полосу, и он всегда начинается со строчной буквы или с середины слова.
"""

import argparse
import json
import os
import re

NUMBERED = re.compile(r"^(?:\(\d{1,3}\)|\[\d{1,3}\]|\d{1,3}[\).]\s|\d{1,3}\s+\S)")
CONTINUES = re.compile(r"^[a-zäöüß(„»]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    restored = []
    for p in pages:
        nl = p.get("note_lines") or []
        if not nl:
            continue
        if any(NUMBERED.match(ln["text"].strip()) for ln in nl):
            continue
        if CONTINUES.match(nl[0]["text"].strip()):
            continue
        p["lines"] = sorted(p["lines"] + nl, key=lambda ln: (ln["top"], ln.get("x0", 0)))
        p["note_lines"] = []
        p["notes"] = []
        restored.append((p["pdf_page"], len(nl), nl[0]["text"].strip()[:60]))

    print(f"врезок возвращено в тело: {len(restored)}")
    for pno, n, head in restored:
        print(f"  f{pno}: строк {n:2d} | {head}")

    if a.dry_run:
        print("\ndry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for p in pages:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: fix_footnote_markers.py")


if __name__ == "__main__":
    main()
