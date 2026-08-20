#!/usr/bin/env python3
"""Разбор номеров сносок под конвенцию этого издания.

    python scripts/fix_footnote_markers.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py: скрипт переписывает поле
`notes` в work/pages.jsonl, а раскладывать сноски по единицам будет сам
пайплайн — у него для этого есть офсеты, которых здесь нет.

Пайплайн ждёт знак сноски со скобкой или точкой («29)», «29.»), потому что
так набирают в большинстве книг. Verlag Österreich ставит голое число:

    29 DazunäherKodekinKonecny,Insolvenz-Forum2003,19.

Из-за этого ни один знак не читается, и вся полоса сносок страницы ложится
одним блоком без номера, а при загрузке такие сноски отсеиваются: в схеме
приёмника номер обязателен и целочисленный. У Insolvenzordnung² так терялось
3175 блоков из 3290, у Iro, Sachenrecht — 226 из 255.

Голое число само по себе слишком слабый признак: австрийские сноски набиты
номерами дел вида «5 Ob 142/68» и «3 Ob 627/82», и они начинают строку
ровно так же. Поэтому номер принимается только если он БОЛЬШЕ предыдущего
принятого на этой же странице: нумерация сносок возрастает, а номер дела
попадает в диапазон случайно и вниз. Первый номер страницы принимается,
только если строка не похожа на продолжение (не начинается с номера дела
вида «5 Ob …»).

Сноска, начатая внизу одной полосы и продолженная вверху следующей, своего
номера на второй полосе не имеет и иметь не может. Такой хвост приписывается
к последней нумерованной сноске предыдущей полосы: иначе он остаётся блоком
без номера, а при загрузке блоки без номера отсеиваются — в схеме приёмника
номер обязателен. У Posch, IPR⁵ так висело 26 хвостов из 27 безномерных
блоков.
"""

import argparse
import json
import os
import re

# «29 Dazu näher …» — знак и сразу текст.
BARE = re.compile(r"^(\d{1,3})\s+(?=\S)")
# Те же три правила под нумерацию длиннее трёх знаков: у выгрузок Westlaw
# сноски нумеруются сквозняком по тому и доходят до «1449.».
# «5 Ob 142/68», «3 Ob 627/82» — номер дела, а не знак сноски. Отделения
# суда мало: «103 Ob die Rechtswahl wirksam ist…» — это сноска 103, начатая
# с немецкого «ob» (ли), и без требования цифры после отделения она теряется.
CASE = re.compile(r"^\d{1,3}\s+(?:Ob|Ob[AS]|Präs|Nc|Fsc|Ds|Nd)\s+\d")
# Знак верхним индексом мог уехать на свою строку.
LONE = re.compile(r"^[\(\[]?(\d{1,3})[\)\].]?$")
# Штатные знаки со скобкой/точкой — их пайплайн читает и сам.
PUNCT = re.compile(r"^(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[\).])\s+(?=\S)")


def widen(digits):
    """Те же правила под номер сноски длиной до `digits` знаков."""
    global BARE, CASE, LONE, PUNCT
    d = "{1,%d}" % digits
    BARE = re.compile(r"^(\d%s)\s+(?=\S)" % d)
    CASE = re.compile(r"^\d%s\s+(?:Ob|Ob[AS]|Präs|Nc|Fsc|Ds|Nd)\s+\d" % d)
    LONE = re.compile(r"^[\(\[]?(\d%s)[\)\].]?$" % d)
    PUNCT = re.compile(r"^(?:\((\d%s)\)|\[(\d%s)\]|(\d%s)[\).])\s+(?=\S)" % (d, d, d))


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
    ap.add_argument("--max-digits", type=int, default=3,
                    help="сколько знаков может быть в номере сноски")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.max_digits != 3:
        widen(a.max_digits)

    path = os.path.join(a.book, "work", "pages.jsonl")
    before = after = pages_touched = unnumbered = carried_merged = 0
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
            out.append(p)

    # Хвост сноски с предыдущей полосы: номера у него нет, приписываем к
    # последней нумерованной сноске той полосы, где сноска началась.
    for prev, cur in zip(out, out[1:]):
        notes = cur.get("notes") or []
        if not notes or not notes[0].get("carried"):
            continue
        host = next((n for n in reversed(prev.get("notes") or [])
                     if n.get("number") is not None), None)
        if host is None:
            continue
        host["text"] = (host.get("text", "") + " " + notes[0].get("text", "")).strip()
        cur["notes"] = notes[1:]
        carried_merged += 1

    for p in out:
        after += len(p.get("notes") or [])
        unnumbered += sum(1 for n in (p.get("notes") or []) if n.get("number") is None)

    print(f"страниц со сносками: {pages_touched}")
    print(f"хвостов с предыдущей полосы прирощено: {carried_merged}")
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
