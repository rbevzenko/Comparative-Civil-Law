#!/usr/bin/env python3
"""Убрать карточки с самозваным номером, влив их текст в предыдущую.

    python scripts/merge_outlier_units.py books/de-mukobgb-* [--max-step 20] [--dry-run]

ЗАЧЕМ. Номер Randnummer восстанавливается в том числе распознаванием, и
изредка на поле оказывается не номер: сбитая цифра сноски, кусок года,
дотянувшийся до правого края. Ряд от этого не теряет текста, но теряет
смысл: у § 994 идут номера 0–69, а следом 990; у § 267 — 1–24, а следом 199.
Отчёт о качестве считает такую единицу законной и объявляет дыру в девятьсот
номеров, а читатель видит в корпусе несуществующий «Rn. 990».

ПРАВИЛО. Внутри параграфа номера идут подряд. Карточка, чей номер больше
предыдущего принятого более чем на `--max-step`, — самозванец: её текст
приклеивается к предыдущей карточке, а сама она выбрасывается. Порог в
двадцать взят с запасом: настоящие пропуски в этих распечатках не превышают
семи номеров подряд.

Текст НЕ теряется: он уходит в соседнюю карточку целиком, вместе со
сносками, последней полосой и концом смещения.
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+")
    ap.add_argument("--max-step", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    total = 0
    for book in a.books:
        path = os.path.join(book, "output", "cards.jsonl")
        if not os.path.exists(path):
            continue
        cards = P.read_jsonl(path)
        # Параграфа может не быть вовсе: у комментария к AktG во вступлении
        # тома номера Rz. идут без параграфа, и сортировка по None падала,
        # обрывая конвейер на предпоследнем шаге.
        order = sorted(range(len(cards)), key=lambda i: (cards[i].get("section") or "",
                                                         cards[i].get("char_start") or 0))
        # Самозванец опознаётся не по одному скачку, а по одиночеству.
        # У § 242 после Rn. 580 идут 700–704 — это настоящие номера, просто
        # часть ряда в распечатку не попала; они образуют СВЯЗНУЮ цепочку
        # (соседи в пределах десяти номеров: у § 242 после 580 идёт 613,
        # потом 619 и дальше подряд до 704 — это один ряд с прорехами).
        # А «990» у § 994 или «199» у § 267 стоят поодиночке, и после них
        # ряд не продолжается. Поэтому выбрасывается только короткая (одна-
        # две карточки) цепочка, оторванная от предыдущей больше чем на
        # --max-step.
        by_sec = defaultdict(list)
        for i in order:
            # Карточка без номера — вступление тома, перетипированное в
            # «Vorspann»: ряда она не образует и в сравнение номеров не идёт.
            if cards[i].get("number") is None:
                continue
            by_sec[cards[i].get("section") or ""].append(i)
        drop = set()
        for sec, idxs in by_sec.items():
            runs = []
            for i in idxs:
                n = cards[i]["number"]
                if runs and n - cards[runs[-1][-1]]["number"] <= 10:
                    runs[-1].append(i)
                else:
                    runs.append([i])
            for k in range(1, len(runs)):
                run = runs[k]
                prev_last = cards[runs[k - 1][-1]]["number"]
                if len(run) <= 2 and cards[run[0]]["number"] > prev_last + a.max_step:
                    host = runs[k - 1][-1]
                    for i in run:
                        h, c = cards[host], cards[i]
                        h["text"] = h["text"] + "\n" + c["text"]
                        h["footnotes"] = h["footnotes"] + c["footnotes"]
                        h["page_end"] = max(h["page_end"], c["page_end"])
                        h["char_end"] = max(h.get("char_end") or 0, c.get("char_end") or 0)
                        drop.add(i)
                        print(f'  {os.path.basename(book)}: § {sec} Rn. {c["number"]} '
                              f'→ влит в Rn. {h["number"]}')
        if not drop:
            continue
        total += len(drop)
        if not a.dry_run:
            P.write_jsonl(path, [c for i, c in enumerate(cards) if i not in drop])
    print(f"снято самозваных номеров: {total}")


if __name__ == "__main__":
    main()
