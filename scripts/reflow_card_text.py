#!/usr/bin/env python3
"""Сборка текста карточки в связный абзац.

    python scripts/reflow_card_text.py --book books/<id> [--lang de] [--dry-run]

Запускать после extract.py, до выгрузки.

В карточку текст попадает так, как он стоял на полосе: со всеми переносами
строк и с переносами СЛОВ по дефису. Читателю и модели достаётся вот это:

    Verpflichtungsgeschäfte begründen obligatorische Ansprüche des Gläu-
    bigers gegen den Schuldner auf künftige Leistungserbringung.

Слово «Gläubigers» здесь разорвано, а строки жёстко обрублены по ширине
полосы — на любой другой ширине текст выглядит рваным. Вдобавок слова в
текстовом слое разделены неразрывным пробелом (U+00A0), из-за чего поиск по
фразе не находит то, что глазом читается.

Скрипт сращивает перенос слова, склеивает строки одного абзаца пробелом и
приводит пробелы к обычным.

Две оговорки, из-за которых это не однострочный replace.

Перенос слова и висячий дефис — разные вещи. В немецком «verbotene, sitten-
oder gesetzwidrige Geschäfte» дефис у «sitten-» СВОЙ, он заменяет вторую
часть сложного слова, и склеивать нельзя: выйдет «sittenoder». Отличает их
следующее слово: если это союз из списка (oder, und, bzw, sowie…), дефис
сохраняется.

Конец абзаца от переноса строки отличает длина: строка, которая заметно
короче остальных в этой карточке, кончает абзац (заголовок, конец мысли), и
перевод строки после неё остаётся.

Отдельно сохраняется начало пункта перечисления («(a)», «(iii)», «(2)»,
«1.», маркер списка): в юридическом тексте каждый подпункт — отдельное
правило, и склеивать их в сплошной абзац значит терять структуру нормы.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import re
import statistics

# Слова, перед которыми дефис в конце строки — висячий, а не перенос.
SUSPENDED = {
    "de": {"oder", "und", "bzw", "beziehungsweise", "sowie", "aber", "als", "wie", "noch"},
    "nl": {"of", "en", "dan", "noch"},
    "fr": {"ou", "et", "ni"},
    "en": {"or", "and", "nor", "to"},
}
SPACES = re.compile(r"[   \t]")

# Перечисление начинает новую строку: «(a)», «(iii)», «(2)», «1.», маркер
# списка. Иначе пункты слипаются в один абзац, и структура нормы, где
# каждый подпункт — отдельное правило, читается как сплошной текст.
ENUM = re.compile(r"^(?:\(\s?(?:[0-9]{1,3}|[a-z]{1,2}|[ivxlcdm]{1,6})\s?\)|[0-9]{1,3}[.)]\s|[•■□▪–—]\s)")


def reflow(text, suspended, short_ratio=0.6):
    text = SPACES.sub(" ", text or "")
    lines = [ln.rstrip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln.strip() or True]
    lengths = [len(ln) for ln in lines if ln.strip()]
    if not lengths:
        return text.strip()
    full = statistics.median(lengths)

    out = ""
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            out = out.rstrip() + "\n"
            continue
        nxt = ""
        for j in range(i + 1, len(lines)):
            if lines[j].strip():
                nxt = lines[j].strip()
                break
        if not out:
            out = stripped
            continue
        prev = out.rstrip()
        # Конец абзаца виден по длине: строка, заметно более короткая, чем
        # остальные в этой карточке, не была обрублена по ширине полосы —
        # она кончилась сама. Перевод строки после неё остаётся.
        # Короткая строка ПОСЕРЕДИНЕ карточки — заголовок, и отбивается с
        # обеих сторон; короткая в конце — просто конец абзаца.
        # Строка, оборванная переносом слова, абзаца не кончает никогда —
        # этот случай разбирается первым.
        if prev.endswith("-"):
            first = re.split(r"[\s,.;:]", stripped, 1)[0].lower().strip("«»\"'")
            out = (prev + " " + stripped) if first in suspended else (prev[:-1] + stripped)
            continue
        if ENUM.match(stripped):
            out = prev + "\n" + stripped
            continue
        ends_para = len(lines[i - 1].strip()) < full * short_ratio
        is_short = len(stripped) < full * short_ratio
        # Короткая строка после законченной фразы — заголовок.
        starts_head = is_short and re.search(r"[.!?»”\"]$", prev) is not None
        if ends_para or starts_head:
            out = prev + "\n" + stripped
            continue
        out = prev + " " + stripped
    return re.sub(r" {2,}", " ", out).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--lang", default="en", choices=sorted(SUSPENDED))
    ap.add_argument("--short-ratio", type=float, default=0.6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    suspended = SUSPENDED[a.lang]
    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    changed = notes = 0
    sample = None
    for c in cards:
        before = c.get("text") or ""
        after = reflow(before, suspended, a.short_ratio)
        if after != before:
            if sample is None:
                sample = (before[:220], after[:220])
            c["text"] = after
            changed += 1
        for fn in c.get("footnotes") or []:
            t = fn.get("text") or ""
            nt = reflow(t, suspended, a.short_ratio)
            if nt != t:
                fn["text"] = nt
                notes += 1

    print(f"карточек перебрано: {changed} из {len(cards)}, сносок: {notes}")
    if sample:
        print("  было: " + repr(sample[0]))
        print("  стало: " + repr(sample[1]))

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
