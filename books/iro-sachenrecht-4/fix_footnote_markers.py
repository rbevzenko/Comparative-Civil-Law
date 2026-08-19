#!/usr/bin/env python3
"""Разбор номеров сносок под конвенцию этого издания.

    python fix_footnote_markers.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py: скрипт переписывает поле
`notes` в work/pages.jsonl, а раскладывать сноски по единицам будет сам
пайплайн — у него для этого есть офсеты, которых здесь нет.

Пайплайн ждёт знак сноски со скобкой или точкой («29)», «29.»), потому что
так набирают в большинстве книг. Verlag Österreich ставит голое число:

    11 Zu§ 1 DenkmalschutzG als gesetzliche Widmung 6 Ob 266/11 b, JBI 2012, …

Из-за этого ни один знак не читается, и вся полоса сносок страницы ложится
одним блоком без номера — в этой книге таких блоков 226 из 255, то есть
структура сносок теряется почти целиком, а при загрузке они отсеиваются
(в схеме приёмника номер сноски обязателен и целочисленный).

Голое число само по себе слишком слабый признак: австрийские сноски набиты
номерами дел вида «5 Ob 142/68» и «3 Ob 627/82», и они начинают строку
ровно так же. Поэтому номер принимается только если он БОЛЬШЕ предыдущего
принятого на этой же странице: нумерация сносок возрастает, а номер дела
попадает в диапазон случайно и вниз. Первый номер страницы принимается,
только если строка не похожа на продолжение (не начинается с номера дела
вида «5 Ob …»).
"""

import argparse
import json
import os
import re

# «29 Dazu näher …» — знак и сразу текст.
BARE = re.compile(r"^(\d{1,3})\s+(?=\S)")
# «5 Ob 142/68», «3 Ob 627/82» — номер дела, а не знак сноски.
CASE = re.compile(r"^\d{1,3}\s+(?:Ob|Ob[AS]|Präs|Nc|Fsc|Ds|Nd)\b")
# Знак верхним индексом мог уехать на свою строку.
LONE = re.compile(r"^[\(\[]?(\d{1,3})[\)\].]?$")
# Штатные знаки со скобкой/точкой — их пайплайн читает и сам.
PUNCT = re.compile(r"^(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[\).])\s+(?=\S)")


def parse_page(note_lines, page):
    notes, cur, pending, last = [], None, None, 0

    def close():
        nonlocal cur
        if cur:
            notes.append(cur)
            cur = None

    for ln in note_lines:
        s = ln["text"].strip()
        if not s:
            continue

        m = LONE.match(s)
        if m:
            close()
            pending = int(m.group(1))
            continue

        num = None
        m = PUNCT.match(s)
        if m:
            num, rest = int(next(g for g in m.groups() if g)), s[m.end():].strip()
        else:
            m = BARE.match(s)
            if m and not CASE.match(s):
                cand = int(m.group(1))
                if cand > last:
                    num, rest = cand, s[m.end():].strip()

        if num is not None:
            close()
            cur = {"number": num, "text": rest, "page": page}
            last, pending = num, None
        elif pending is not None:
            close()
            cur = {"number": pending, "text": s, "page": page}
            last, pending = pending, None
        elif cur:
            cur["text"] += " " + s
        else:
            # Хвост сноски с предыдущей страницы: номера у него нет и быть
            # не может, но терять текст нельзя.
            cur = {"number": None, "page": page, "carried": True, "text": s}
    close()
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    before = after = pages_touched = unnumbered = 0
    out = []
    sample = []

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            old = p.get("notes") or []
            before += len(old)
            if p.get("note_lines"):
                new = parse_page(p["note_lines"], p.get("printed_page") or p["pdf_page"])
                if new:
                    if len(sample) < 3 and len(new) > 2:
                        sample.append((p["pdf_page"], old, new))
                    p["notes"] = new
                    pages_touched += 1
            after += len(p.get("notes") or [])
            unnumbered += sum(1 for n in (p.get("notes") or []) if n.get("number") is None)
            out.append(p)

    print(f"страниц со сносками: {pages_touched}")
    print(f"сносок было: {before} → стало: {after}, из них без номера: {unnumbered}")
    for pg, old, new in sample:
        print(f"\n  f{pg} было {len(old)}: {json.dumps(old[:1], ensure_ascii=False)[:150]}")
        print(f"       стало {len(new)}:")
        for n in new[:4]:
            print(f"         {n['number']}: {n['text'][:70]}")

    if a.dry_run:
        print("\ndry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for p in out:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: extract.py заново — он разложит сноски по единицам сам")


if __name__ == "__main__":
    main()
