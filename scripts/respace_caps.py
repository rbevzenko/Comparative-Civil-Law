#!/usr/bin/env python3
"""Расклейка слов в строках, набранных прописными вразрядку.

    python scripts/respace_caps.py --book <каталог> --pdf book.pdf [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

В текстовом слое этих книг пробелов нет: слова разделены только положением
символов. pipelib._space_gap берёт порог как 0.35 от медианной ширины
символа строки, и на основном тексте это работает. На заголовке, набранном
прописными вразрядку, — нет: у Snell's Equity в строке
«THE NATURE, HISTORY AND COURTS OF EQUITY» медианная ширина символа 7.2,
порог выходит 2.52, а межсловный зазор там 2.13–2.49. Заголовок склеивается
в «THENATURE,HISTORYANDCOURTSOFEQUITY» — и именно он идёт в иерархию
карточек как название главы.

Понижать порог для всей книги нельзя: на основном тексте он тогда разорвёт
слова по кернингу. Поэтому скрипт трогает только строки с длинной цепочкой
прописных без пробела и пересобирает слова заново по символам из PDF, взяв
порог мягче (--factor). Зазоры кернинга в таких строках нулевые или
отрицательные, межсловные — заметно больше, так что разделяются они чисто.
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
import statistics
import sys

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")

GLUED = re.compile(r"[A-ZÀ-Þ]{9,}")


def resplit(chars, factor):
    chars = sorted(chars, key=lambda c: c["x0"])
    widths = [c["x1"] - c["x0"] for c in chars if c["x1"] > c["x0"]]
    gap = max(0.8, (statistics.median(widths) if widths else 4.0) * factor)
    words, buf, prev = [], [], None
    for ch in chars:
        if prev is not None and ch["x0"] - prev > gap:
            if buf:
                words.append(buf)
            buf = []
        buf.append(ch)
        prev = ch["x1"]
    if buf:
        words.append(buf)
    return [{"text": "".join(c["text"] for c in w).strip(),
             "x0": min(c["x0"] for c in w), "x1": max(c["x1"] for c in w),
             "top": min(c["top"] for c in w), "bottom": max(c["bottom"] for c in w),
             "size": round(statistics.median([c["size"] for c in w]), 2)}
            for w in words if "".join(c["text"] for c in w).strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--factor", type=float, default=0.15,
                    help="доля медианной ширины символа, считающаяся пробелом")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    todo = {p["pdf_page"] for p in rows
            if any(GLUED.search(ln["text"]) for ln in p.get("lines") or [])}
    if not todo:
        print("склеенных прописных строк нет")
        return

    fixed = 0
    sample = []
    with pdfplumber.open(a.pdf) as pdf:
        for p in rows:
            if p["pdf_page"] not in todo:
                continue
            chars = pdf.pages[p["pdf_page"] - 1].chars
            for ln in p.get("lines") or []:
                if not GLUED.search(ln["text"]):
                    continue
                own = [c for c in chars
                       if ln["x0"] - 0.5 <= c["x0"] and c["x1"] <= ln["x1"] + 0.5
                       and ln["top"] - 0.5 <= c["top"] and c["bottom"] <= ln["bottom"] + 0.5]
                if not own:
                    continue
                words = resplit(own, a.factor)
                text = " ".join(w["text"] for w in words).strip()
                if text == ln["text"] or not text:
                    continue
                if len(sample) < 12:
                    sample.append((p["pdf_page"], ln["text"][:70], text[:70]))
                ln["words"], ln["text"] = words, text
                fixed += 1

    print(f"строк пересобрано: {fixed} на {len(todo)} полосах")
    for pno, before, after in sample:
        print(f"  f{pno}: {before!r}\n      → {after!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for p in rows:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
