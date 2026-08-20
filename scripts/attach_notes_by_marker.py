#!/usr/bin/env python3
"""Раскладка сносок по карточкам не по полосе, а по знаку в тексте.

    python scripts/attach_notes_by_marker.py --book books/<id> [--dry-run]

Запускать ПОСЛЕ extract.py (и после fix_footnote_markers.py), до отчёта.

Штатный `attach_notes` в extract.py считает, что сноска стоит на той же
полосе, что и знак: так свёрстана бумажная книга. У выгрузки Westlaw/ProView
это не так — блок сносок собирается не на каждой полосе, а раз в несколько
полос, и часть их вынесена в конец главы. У Chitty vol.1 сноски нашлись на
1289 полосах из 2525, и сноски получили 18% карточек, хотя разобрано их
почти девятнадцать тысяч.

Здесь связь восстанавливается по самому знаку. Нумерация сносок в такой
книге сквозная внутри главы и возрастает, знак стоит в тексте ровно один раз
и в том же порядке. Поэтому карточки главы обходятся подряд, а номера сносок
выдаются по очереди: пока ожидаемый номер находится в тексте карточки
отдельным числом, сноска приписывается ей.

Пропуск знака (в текстовом слое он иногда слипается с числом рядом) не
должен останавливать раскладку: если ожидаемого номера нет, а следующие за
ним есть, пропущенные приписываются той же карточке — потерять сноску хуже,
чем поставить её на абзац раньше.
"""

import argparse
import json
import os
import re
from collections import defaultdict


def card_pos(card):
    page = card.get("page_start")
    box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
    return (page if page is not None else 10 ** 6, box["bbox"][1] if box else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--lookahead", type=int, default=3,
                    help="сколько пропущенных знаков подряд прощать")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    notes_by_page = {}
    for line in open(os.path.join(a.book, "work", "pages.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        notes = [n for n in (p.get("notes") or []) if n.get("number") is not None]
        if notes:
            notes_by_page[p["pdf_page"]] = notes

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    order = sorted(cards, key=card_pos)

    # Раздел (глава) → его карточки по порядку и полосы, на которых он живёт.
    # Полосы берутся до начала следующего раздела: блок сносок, вынесенный в
    # конец главы, стоит уже после последней её карточки.
    by_section, seq = defaultdict(list), []
    for c in order:
        sec = c.get("section")
        if not seq or seq[-1] != sec:
            seq.append(sec)
        by_section[sec].append(c)

    starts = {sec: min(card_pos(c)[0] for c in cs) for sec, cs in by_section.items()}
    bounds = {}
    for i, sec in enumerate(seq):
        nxt = starts[seq[i + 1]] if i + 1 < len(seq) else 10 ** 6
        bounds[sec] = (starts[sec], nxt - 1)

    attached = orphan = skipped = 0
    for sec in seq:
        lo, hi = bounds[sec]
        notes = [n for pg in sorted(notes_by_page) if lo <= pg <= hi
                 for n in notes_by_page[pg]]
        if not notes:
            continue
        pool = {}
        for n in notes:
            pool.setdefault(n["number"], n)
        pending = sorted(pool)
        k = 0
        for card in by_section[sec]:
            text = card.get("text") or ""
            here = []
            while k < len(pending):
                want = pending[k]
                if re.search(r"(?<!\d)%d(?!\d)" % want, text):
                    here.append(pool[want])
                    k += 1
                    continue
                # Знак мог слипнуться с соседним числом: если следующие за ним
                # знаки в этой же карточке есть, пропущенный отдаётся ей же.
                ahead = [j for j in range(k + 1, min(k + 1 + a.lookahead, len(pending)))
                         if re.search(r"(?<!\d)%d(?!\d)" % pending[j], text)]
                if not ahead:
                    break
                for j in range(k, ahead[-1] + 1):
                    here.append(pool[pending[j]])
                skipped += ahead[-1] - k
                k = ahead[-1] + 1
            if here:
                card["footnotes"] = sorted(here, key=lambda n: n["number"])
                attached += len(here)
        orphan += len(pending) - k

    with_notes = sum(1 for c in cards if c.get("footnotes"))
    print(f"сносок разложено: {attached}, не нашли своего знака: {orphan}, "
          f"знаков пропущено: {skipped}")
    print(f"карточек со сносками: {with_notes} из {len(cards)} "
          f"({round(100 * with_notes / max(1, len(cards)))}%)")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
