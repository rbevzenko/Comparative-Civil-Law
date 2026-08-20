#!/usr/bin/env python3
"""Чистка заголовков иерархии от следов вёрстки.

    python clean_hierarchy.py --book <каталог> [--dry-run]

Запускать после extract.py, до отчёта о качестве.

Иерархию этой книги пайплайн берёт из зашитого в файл оглавления — оно
полное и точное по структуре (139 узлов, шесть уровней), но заголовки в нём
записаны так, как их отдал вёрстальный пакет, а не так, как они читаются:

    § 11. Familienrecht1                       ← знак сноски прилип к слову
    3. Der Inhalt der Rom I-Verordnung 37      ← и здесь, только через пробел
    … (Art 30–52 CISG) . . 19/20               ← отточие и номер единицы
    C. DieWende im kollisionsrechtlichen …     ← потерян пробел на стыке слов
    § 17. … Terminologie,Kategorien            ← и после запятой
    … UN-Über-einkommen“ (CISG)                ← перенос строки застыл дефисом

Иерархия видна человеку в карточке, и «Familienrecht1» в ней — это не
косметика, а вопрос доверия к источнику.

Правила ниже намеренно узкие, а переносы разбираются вовсе по списку: общее
правило «дефис перед строчной буквой — это перенос» съело бы
«Business-to-Business-Verträge», а таких заголовков в книге два.
"""

import argparse
import json
import os
import re

LEADER = re.compile(r"\s*(?:\.\s*)+\d{1,2}/\d{1,3}\s*$")     # « . . 19/20»
NOTE_GLUED = re.compile(r"(?<=[a-zäöüß])\d{1,2}$")           # «Familienrecht1»
NOTE_SPACED = re.compile(r"(?<=[a-zäöüß]{4})\s\d{1,2}$")     # «… Verordnung 37»
COMMA = re.compile(r",(?=[A-ZÄÖÜ])")                          # «Terminologie,Kategorien»
# Стык слов без пробела. Строчных перед прописной требуется не меньше двух:
# иначе правило разорвало бы «eBusiness», а он в книге пишется именно так.
GLUED = re.compile(r"(?<=[a-zäöüß]{2})(?=[A-ZÄÖÜ][a-zäöü])")
HYPHENS = {
    "Sach-verhalten": "Sachverhalten",
    "auf-einanderfolgende": "aufeinanderfolgende",
    "Auf-trag": "Auftrag",
    "Über-einkommen": "Übereinkommen",
}


def clean(title):
    out = LEADER.sub("", title)
    out = NOTE_GLUED.sub("", out)
    out = NOTE_SPACED.sub("", out)
    out = COMMA.sub(", ", out)
    out = GLUED.sub(" ", out)
    for bad, good in HYPHENS.items():
        out = out.replace(bad, good)
    return re.sub(r"\s{2,}", " ", out).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    changes, touched = {}, 0
    for c in cards:
        new = []
        hit = False
        for h in c.get("hierarchy") or []:
            fixed = clean(h)
            if fixed != h:
                changes[h] = fixed
                hit = True
            new.append(fixed)
        if hit:
            touched += 1
        c["hierarchy"] = new

    print(f"узлов исправлено: {len(changes)}, карточек затронуто: {touched} из {len(cards)}")
    for old in sorted(changes):
        print(f"  {old!r}\n  → {changes[old]!r}")

    if a.dry_run:
        print("\ndry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for c in cards:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: qa_report.py")


if __name__ == "__main__":
    main()
