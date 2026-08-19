#!/usr/bin/env python3
"""Иерархия карточек по заголовкам в теле полосы.

    python scripts/hierarchy_from_headings.py --book books/<id> \
        --level '^Titre\\s+\\d' --level '^Chapitre\\s+\\d' --level '^Section\\s+\\d' [--dry-run]

Запускать после extract.py, до отчёта о качестве.

Для книг, у которых нет ни зашитого оглавления, ни печатного: у бельгийских
парламентских документов иерархия видна только в самом тексте — «Titre 1er –
Les sûretés personnelles», «Chapitre 2 – La sûreté personnelle accessoire»,
«Section 4 – L’extinction du cautionnement». Без неё карточка приходит в
корпус без единого слова о том, к какому институту относится.

Порядок `--level` задаёт уровни вложенности: первый флаг — верхний уровень.
Заголовок сбрасывает все уровни ниже своего.

Заголовок, не поместившийся в строку, продолжается следующей строкой; она
опознаётся по строчной букве в начале и приклеивается. Иначе в иерархию
попадает «Section 2 – Les effets du cautionnement entre le» с обрывом на
предлоге. Перенос по дефису при этом сращивается, а обрывок из одной-двух
букв продолжением не считается: у «1er» верхний индекс уезжает отдельной
строкой, и без этой оговорки заголовок кончается словом «er».
"""

import argparse
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--level", action="append", required=True,
                    help="регулярное выражение уровня; порядок флагов = порядок вложенности")
    ap.add_argument("--title-on-next", action="store_true",
                    help="заголовок состоит из одного номера, название — следующей строкой")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    levels = [re.compile(rx) for rx in a.level]
    pages = {}
    for line in open(os.path.join(a.book, "work", "pages.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        pages[p["pdf_page"]] = p

    marks = []          # (полоса, доля высоты, уровень, заголовок)
    for pno in sorted(pages):
        page = pages[pno]
        H = page["height"] or 1
        lines = page["lines"]
        for i, ln in enumerate(lines):
            text = " ".join(ln["text"].split())
            depth = next((d for d, rx in enumerate(levels) if rx.match(text)), None)
            if depth is None:
                continue
            nxt = " ".join(lines[i + 1]["text"].split()) if i + 1 < len(lines) else ""
            # У части документов заголовок состоит из одного номера («TITRE 1»),
            # а название стоит следующей строкой и начинается с прописной.
            # Отличить её от начала текста можно по самому заголовку: пока в
            # нём нет ничего, кроме слова и номера, названия у него нет.
            if (a.title_on_next and len(text.split()) <= 2 and nxt
                    and not any(rx.match(nxt) for rx in levels)):
                text = f"{text}. {nxt}"
                nxt = " ".join(lines[i + 2]["text"].split()) if i + 2 < len(lines) else ""
            if len(nxt) > 2 and nxt[:1].islower():
                text = f"{text[:-1]}{nxt}" if text.endswith("-") else f"{text} {nxt}"
            text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
            text = re.sub(r"\s+(?:er|re|e|ère)$", "", text)
            marks.append((pno, ln["top"] / H, depth, " ".join(text.split())))

    print(f"заголовков найдено: {len(marks)}")
    for pno, top, depth, text in marks[:8]:
        print(f"  f{pno} уровень {depth}: {text[:64]}")

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    def start_of(card):
        page = card.get("page_start")
        box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
        return (page if page is not None else 10 ** 6, box["bbox"][1] if box else 0.0)

    filled = 0
    for card in cards:
        pos = start_of(card)
        stack = {}
        for pno, top, depth, text in marks:
            if (pno, top) > pos:
                break
            stack[depth] = text
            for deeper in [d for d in stack if d > depth]:
                del stack[deeper]
        path_nodes = [stack[d] for d in sorted(stack)]
        if path_nodes:
            card["hierarchy"] = path_nodes
            filled += 1

    print(f"карточек с иерархией: {filled} из {len(cards)}")
    if cards:
        print(f"  пример: {cards[-1]['external_id']} → {' › '.join(cards[-1].get('hierarchy') or [])}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
