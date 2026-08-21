#!/usr/bin/env python3
"""Починка номеров статей, разбитых распознаванием.

    python scripts/fix_ocr_article_numbers.py --book books/<id> [--dry-run]

Запускать МЕЖДУ pages_digital.py и extract.py: правится модель полосы, и
дальше вся сборка идёт по исправленным строкам.

У PEL Unjustified Enrichment распознавание систематически путает цифры с
буквами внутри номера: «Article 2: IOI» вместо 2:101, «Article 4: I OS»
вместо 4:105, «Article 6: IO/ · Disenrichment» вместо 6:101. Ноль читается
как O, единица как I, J или дробь, пятёрка как S. Шаблон единицы такие
заголовки не видит вовсе — в книге на сотню статей находилось три.

Правка узкая и потому безопасная:

* строка должна НАЧИНАТЬСЯ со слова Article (допускается его собственная
  порча: Artlcle, Artfcle, Anicle);
* дальше цифра главы, разделитель, и ровно три знака номера из набора
  «цифры и их обычные подмены»;
* после подстановки должны получиться ТРИ ЦИФРЫ — иначе строка не
  трогается вовсе.

Внутри текста ничего не правится: «perfor1nance» и «tl1e» остаются как
есть. Чинить прозу вслепую нельзя, а номер — это адрес, и его порча ломает
саму возможность сослаться.
"""

import argparse
import json
import os
import re

# Подмены, которые делает распознаватель в цифрах этого набора.
DIGIT = {"I": "1", "l": "1", "J": "1", "/": "1", "|": "1",
         "O": "0", "o": "0", "Q": "0", "S": "5", "s": "5",
         "B": "8", "g": "9", "Z": "2"}

# Внутри самого слова тоже бывает разрыв: «Art icle 4: I 03». Пробелы
# допускаются между любыми буквами — строка всё равно обязана начинаться
# с него и продолжаться номером, так что ложных срабатываний это не даёт.
HEAD = re.compile(r"^(A\s*[rn]\s*[tf]\s*[il]\s*c\s*[il]\s*e)\s*(\d)\s*[:;.,]\s*([0-9IlJ/|OoQSsBgZ][0-9IlJ/|OoQSsBgZ\s]{1,6}?)\s*[:;.,\-·]\s*(\S.*)$")


def repair(text):
    m = HEAD.match(text)
    if not m:
        return None
    raw = m.group(3).replace(" ", "")
    num = "".join(DIGIT.get(ch, ch) for ch in raw)
    if not (len(num) == 3 and num.isdigit()):
        return None
    return f"Article {m.group(2)}:{num}: {m.group(4)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    fixed, examples = 0, []
    for pg in pages:
        for ln in pg["lines"]:
            new = repair(ln["text"])
            if new and new != ln["text"]:
                if len(examples) < 8:
                    examples.append((pg["pdf_page"], ln["text"][:52], new[:52]))
                ln["text"] = new
                fixed += 1

    print(f"починено заголовков: {fixed}")
    for p, old, new in examples:
        print(f"   полоса {p}: «{old}» → «{new}»")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
