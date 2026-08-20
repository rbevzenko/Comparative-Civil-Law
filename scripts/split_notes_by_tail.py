#!/usr/bin/env python3
"""Отделение сносок как ХВОСТА полосы, набранного мелким кеглем.

    python scripts/split_notes_by_tail.py --book <каталог> --size-max 12 [--dry-run]

Запускать ПОСЛЕ pages_digital.py (с `footnotes.mode: none`) и ДО
fix_footnote_markers.py.

Штатный font_bottom решает по каждой строке отдельно: мельче порога и ниже
полосы — значит сноска. Там, где мелким кеглем набраны не только сноски, это
рвёт текст. У Treitel (Peel), The Law of Contract, 14th ed. кеглем 10.8
набраны СРАЗУ ТРИ вещи: сноски, выключные цитаты внутри абзаца и заголовки
разделов («2. ACCEPTANCE»). Кегль их не различает вовсе — на живом прогоне
выключная цитата уезжала в аппарат, а вместе с ней из карточки пропадал
кусок рассуждения.

Различает положение: блок сносок стоит В КОНЦЕ полосы, и после него текста
тела уже нет. Выключная цитата и заголовок — внутри потока, под ними снова
идёт тело. Поэтому сноски здесь — непрерывный хвост мелких строк до нижнего
края полосы, а не всякая мелкая строка ниже порога.

Полоса, целиком набранная мелким кеглем (в этой вёрстке аппарат занимает и
целые полосы подряд), оказывается хвостом целиком — это верно.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--size-max", type=float, required=True,
                    help="кегль, ниже которого строка может быть сноской")
    ap.add_argument("--min-lines", type=int, default=1,
                    help="сколько строк минимум должно быть в хвосте")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]
    moved = touched = kept_inline = 0
    sample = []

    for pg in pages:
        lines = pg.get("lines") or []
        if not lines:
            continue
        cut = len(lines)
        while cut > 0 and (lines[cut - 1].get("size") or 99) <= a.size_max:
            cut -= 1
        tail = lines[cut:]
        if len(tail) < a.min_lines:
            continue
        # Мелкие строки, оставшиеся выше хвоста, — это выключные цитаты и
        # заголовки: они остаются в теле, там их место.
        kept_inline += sum(1 for ln in lines[:cut] if (ln.get("size") or 99) <= a.size_max)
        if len(sample) < 4 and cut > 0:
            sample.append((pg["pdf_page"], lines[cut - 1]["text"][:45], tail[0]["text"][:45]))
        pg["lines"] = lines[:cut]
        pg["note_lines"] = (pg.get("note_lines") or []) + tail
        pg["notes"] = []
        moved += len(tail)
        touched += 1

    print(f"полос с блоком сносок: {touched}, строк в аппарат: {moved}")
    print(f"мелких строк оставлено в теле (цитаты, заголовки): {kept_inline}")
    for pno, last_body, first_note in sample:
        print(f"  f{pno}: тело …{last_body!r} | аппарат {first_note!r}…")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
