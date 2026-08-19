#!/usr/bin/env python3
"""Отделение блока сносок по отбивке, а не по кеглю и не по полосе.

    python split_footnotes.py --book <каталог> [--gap 2.0] [--dry-run]

Запускать сразу после pages_digital.py и ДО fix_footnote_markers.py.
Профиль этой книги идёт с `footnotes.mode: none` — весь разбор здесь.

В этой книге ни кегль, ни положение сносок не отделяют. Кегль 7.5 несёт
разом три разные вещи:

    idF BGBl I 1997/114                       ← справка о редакции
    Literatur: Birnbauer, Geschäftsführer…    ← список в начале параграфа
    19 Koppensteiner/Rüffler, GmbHG3 §18 Rz20 ← собственно сноска

Положение тоже не помогает. Настоящий блок сносок начинается в среднем на
0.71 высоты полосы, но на плотных полосах поднимается до 0.28, а список
Literatur на первой полосе параграфа занимает всю полосу от 0.11 донизу.
Любая полоса, взятая достаточно низко, чтобы поймать все сноски, разрезает
списки Literatur пополам.

Решают два признака, и порядок между ними важен.

Первый — что стоит в НАЧАЛЕ хвоста. Аппарат называет себя сам: «Literatur:»,
«idF BGBl…», «Inhaltsübersicht». Сноска начинается с голого номера. Признак
точный, но неполный: сноска, перенесённая с предыдущей полосы, начинается с
середины фразы и номера не имеет вовсе.

Второй, для этого остатка, — отбивка. Аппарат параграфа набран в поток, с
обычным интерлиньяжем (медиана разрыва 1.5), блок сносок отбит (медиана 3.1).
Одной отбивки не хватило бы: замер по всем 2002 полосам тела показал, что в
зоне 1.75–2.25 признаки перемешаны — там и списки Literatur с широкой
отбивкой, и сноски с узкой. Поэтому отбивка решает только там, где первый
признак молчит, и на таких полосах разброс уже не мешает: перенос сноски
всегда отбит шире, чем продолжение списка.
"""

import argparse
import json
import os
import re
import statistics

NOTE_MAX = 7.6      # тело 8.5, аппарат и сноски 7.5, знаки сносок 5.5
DIGIT = re.compile(r"^\d{1,3}\s*\S")
APPARATUS = re.compile(r"^(?:Literatur\b|idF\b|Inhaltsübersicht\b|Übersicht\b)")


def kind_of_head(text):
    """Что это за хвост, если он называет себя сам."""
    s = text.strip()
    if APPARATUS.match(s):
        return "body"
    if DIGIT.match(s):
        return "notes"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--gap", type=float, default=2.0, help="во сколько интерлиньяжей отбит блок сносок")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    split = kept = allsmall = 0
    by_head = by_gap = 0
    gaps_notes, gaps_body, samples = [], [], []
    prev_kind = "body"
    for p in sorted(pages, key=lambda x: x["pdf_page"]):
        ls = p.get("lines") or []
        p["note_lines"], p["notes"] = [], []
        if not ls:
            continue
        k = len(ls)
        while k > 0 and (ls[k - 1].get("size") or 99) <= NOTE_MAX:
            k -= 1
        if k == len(ls):
            prev_kind = "body"
            continue                      # мелкого хвоста нет вовсе

        head = kind_of_head(ls[k]["text"])
        if k == 0:
            # Полоса целиком мелкая: продолжение либо списка Literatur, либо
            # блока сносок. Отбивки здесь нет; если и начало молчит —
            # наследуем от предыдущей полосы.
            allsmall += 1
            kind = head or prev_kind
            ratio = None
        else:
            tops = sorted(l["top"] for l in ls)
            steps = [b - a_ for a_, b in zip(tops, tops[1:]) if b > a_]
            pitch = statistics.median(steps) if steps else 10.0
            ratio = (ls[k]["top"] - ls[k - 1]["top"]) / pitch
            if head is not None:
                kind = head
                by_head += 1
            else:
                kind = "notes" if ratio >= a.gap else "body"
                by_gap += 1

        if kind == "notes":
            p["note_lines"], p["lines"] = ls[k:], ls[:k]
            split += 1
            if ratio is not None:
                gaps_notes.append(ratio)
            if len(samples) < 3 and k:
                samples.append((p["pdf_page"], round(ratio or 0, 1), ls[k]["text"][:56]))
        else:
            kept += 1
            if ratio is not None:
                gaps_body.append(ratio)
        prev_kind = kind

    print(f"полос: {len(pages)}")
    print(f"  блок сносок отделён:             {split}")
    print(f"  хвост оставлен в теле (аппарат):  {kept}")
    print(f"  полос целиком мелким кеглем:      {allsmall}")
    print(f"  решено по началу хвоста: {by_head}, по отбивке: {by_gap}")
    if gaps_notes and gaps_body:
        print(f"  отбивка у сносок:   мин {min(gaps_notes):.1f}, медиана {statistics.median(gaps_notes):.1f}")
        print(f"  отбивка у аппарата: макс {max(gaps_body):.1f}, медиана {statistics.median(gaps_body):.1f}")
    for pno, r, head_txt in samples:
        print(f"  f{pno} отбивка {r}× | {head_txt}")

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
