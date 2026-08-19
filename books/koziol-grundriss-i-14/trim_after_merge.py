#!/usr/bin/env python3
"""Обрезка хвоста карточки, куда затёк текст соседней единицы.

    python trim_after_merge.py --book <каталог книги> [--dry-run]

Запускать ПОСЛЕ merge_units.py. Там, где основной прогон не распознал
маргинальный номер (скан прочитал «166» как «l 66»), единица не начиналась —
и её текст дописывался к предыдущей карточке. Сверочный прогон этот номер
нашёл, карточка перенесена, но у предыдущей хвост так и остался: один и тот
же абзац лежит в корпусе дважды, причём в старшей карточке он ещё и подписан
чужим адресом. Для корпуса цитирования это хуже, чем дыра в нумерации:
цитата уезжает не на ту Rz.

Граница не выдумывается — её принёс сверочный прогон. Начало перенесённой
карточки ищется в хвосте предыдущей выравниванием по словам (difflib), а не
поиском подстроки: распознавание у двух прогонов разное, дословного
совпадения нет. Режется только при уверенном совпадении, всё остальное
показывается человеку и остаётся как есть.
"""

import argparse
import difflib
import json
import os
import re
import sys

MIN_BLOCK = 25          # слов в общем куске; короче — совпадение случайное
TAIL_SLACK = 5          # насколько общий кусок может не доходить до конца карточки


def words_with_offsets(text):
    return [(m.group(0), m.start()) for m in re.finditer(r"\S+", text)]


def key(w):
    return re.sub(r"[^0-9a-zA-ZäöüßÄÖÜ]+", "", w).lower()


def find_cut(prev_text, moved_text):
    """Смещение в prev_text, с которого начинается затёкший текст соседа.

    Признак затекания — не совпадение начал, а общий кусок, доходящий до
    КОНЦА предыдущей карточки: так выглядит хвост, который на самом деле
    принадлежит следующей единице. Совпадения начал требовать нельзя —
    перенесённая карточка нередко начинается с материала, который основной
    прогон отнёс к сноскам, и её первые слова в предыдущей просто не стоят.
    """
    prev = words_with_offsets(prev_text)
    moved = words_with_offsets(moved_text)
    if len(prev) < MIN_BLOCK or len(moved) < MIN_BLOCK:
        return None, 0

    a = [key(w) for w, _ in prev]
    b = [key(w) for w, _ in moved]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks = [bl for bl in sm.get_matching_blocks() if bl.size >= MIN_BLOCK]
    # Кусок должен упираться в конец предыдущей карточки, иначе это просто
    # похожий абзац где-то в середине, и резать по нему нельзя.
    blocks = [bl for bl in blocks if bl.a + bl.size >= len(a) - TAIL_SLACK]
    if not blocks:
        return None, 0

    anchor = min(blocks, key=lambda bl: bl.a)
    return prev[anchor.a][1], anchor.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    merged = [c for c in cards if c.get("merged_from")]
    if not merged:
        sys.exit("в корпусе нет перенесённых карточек — сначала merge_units.py")

    by_number = {}
    for c in cards:
        if str(c.get("unit_number", "")).isdigit():
            by_number[int(c["unit_number"])] = c

    trimmed, kept = [], []
    for c in merged:
        n = int(c["unit_number"])
        prev = by_number.get(n - 1)
        if prev is None or prev.get("merged_from"):
            continue
        cut, size = find_cut(prev["text"], c["text"])
        if cut is None:
            kept.append((prev, c, size))
            continue
        tail = prev["text"][cut:]
        trimmed.append((prev, c, size, len(tail)))
        if not a.dry_run:
            prev["text"] = prev["text"][:cut].rstrip()
            # Офсеты в book.txt после обрезки указывали бы на чужой конец.
            prev["char_end"] = None
            prev["trimmed_for"] = c["external_id"]

    print(f"перенесённых карточек: {len(merged)}, обрезано предыдущих: {len(trimmed)}")
    for prev, c, size, cut_len in trimmed:
        print(f"  Rz {prev['unit_number']}: снято {cut_len} симв. из {len(prev['text'])}, "
              f"общий кусок с Rz {c['unit_number']} — {size} слов")
        if a.dry_run:
            head = ' '.join(prev['text'][:cut_len and None].split())
            print(f"      остаётся: …{' '.join(prev['text'][:len(prev['text']) - cut_len].split())[-100:]}")
            print(f"      снимается: {' '.join(prev['text'][len(prev['text']) - cut_len:].split())[:100]}…")
    for prev, c, size in kept:
        print(f"  Rz {prev['unit_number']}: не тронута — хвоста Rz {c['unit_number']} в ней нет")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")
    print("Дальше: qa_report.py заново и upload_corpus.py — загрузка идемпотентна по external_id")


if __name__ == "__main__":
    main()
