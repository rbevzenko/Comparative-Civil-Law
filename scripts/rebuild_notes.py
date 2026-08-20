#!/usr/bin/env python3
"""Пересборка аппарата сносок из строк блока сносок.

    python scripts/rebuild_notes.py --book <каталог> [--max-digits 3] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

`parse_notes` в pipelib разбирает блок сносок по знаку, вынесенному верхним
индексом. У книг, где номер сноски набран тем же кеглем, что её текст, и
отделён от него простым пробелом — «29 See V. Finch, ‘Control and
Co-ordination in Corporate Rescue’ (2005) 25 OJLS 374» — этого знака нет, и
весь блок ложится одной сноской без номера. У Finch, Corporate Insolvency
Law так вышло у 726 блоков из 743.

Здесь правило простое и достаточное для таких книг: строка, начинающаяся с
числа и пробела, открывает новую сноску; всё до следующего такого числа —
её текст. Число принимается, только если оно продолжает счёт: больше
предыдущего или равно 1 (нумерация сносок перезапускается в начале главы).
Иначе строка, начинающаяся с года или суммы, рвала бы аппарат.

Две короткие сноски помещаются в одну строку («10 Cornish and Clark, Law
and Society, p. 232. 11 Ibid., p. 234.») — такая строка режется по
СЛЕДУЮЩЕМУ ожидаемому номеру. От ссылки на страницу («pp. 11 ff.») его
отличают два условия сразу: номер ровно last+1 и заглавная буква следом.

Отступ продолжения тут не нужен: он есть не у всех книг, а счёт номеров
есть всегда.
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
    ap.add_argument("--max-digits", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    marker = re.compile(r"^(\d{1,%d})\s+(\S.*)$" % a.max_digits)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    last = 0
    built = pages_touched = 0
    sample = []
    for pg in pages:
        nl = pg.get("note_lines") or []
        if not nl:
            continue
        notes, cur = [], None
        for ln in nl:
            t = (ln.get("text") or "").strip()
            if not t:
                continue
            m = marker.match(t)
            num = int(m.group(1)) if m else None
            if num is not None and (num > last or num == 1):
                if cur:
                    notes.append(cur)
                cur = {"number": num, "text": m.group(2).strip(),
                       "page": pg.get("printed_page") or pg["pdf_page"]}
                last = num
                # Две короткие сноски помещаются в одну строку: «10 Cornish
                # and Clark, Law and Society, p. 232. 11 Ibid., p. 234.»
                # Режем по СЛЕДУЮЩЕМУ ожидаемому номеру. От ссылки
                # на страницу («pp. 11 ff.») его отличают два условия сразу:
                # номер ровно last+1 и заглавная буква следом.
                while True:
                    nxt = re.search(r"(?<!\d)\s%d\s+(?=[A-Z‘“\"(])" % (last + 1), cur["text"])
                    if not nxt:
                        break
                    head, tail = cur["text"][:nxt.start()], cur["text"][nxt.end():]
                    cur["text"] = head.strip()
                    notes.append(cur)
                    last += 1
                    cur = {"number": last, "text": tail.strip(),
                           "page": pg.get("printed_page") or pg["pdf_page"]}
                continue
            if cur is None:
                continue
            cur["text"] = (cur["text"] + " " + t).strip()
        if cur:
            notes.append(cur)
        notes = [n for n in notes if n["text"]]
        if not notes:
            # Поле переписывается всегда: оставить прежний разбор значит
            # оставить блок без номера, который всё равно не загрузится, зато
            # попадёт в отчёт как «сноска без читаемого номера».
            if not a.dry_run:
                pg["notes"] = []
            continue
        pages_touched += 1
        built += len(notes)
        if len(sample) < 3:
            sample.append((pg["pdf_page"], [(n["number"], n["text"][:40]) for n in notes[:3]]))
        if not a.dry_run:
            pg["notes"] = notes

    print(f"сносок собрано: {built} на {pages_touched} полосах")
    for pno, ex in sample:
        print(f"  f{pno}: {ex}")
    if a.dry_run:
        print("--dry-run: файл не изменён")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
