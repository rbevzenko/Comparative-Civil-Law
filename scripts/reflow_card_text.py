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
приводит пробелы к обычным. Мягкий перенос U+00AD снимается вместе с
переводом строки: висячим дефисом он не бывает, его ставит только вёрстка.

Две оговорки, из-за которых это не однострочный replace.

Перенос слова и висячий дефис — разные вещи. В немецком «verbotene, sitten-
oder gesetzwidrige Geschäfte» дефис у «sitten-» СВОЙ, он заменяет вторую
часть сложного слова, и склеивать нельзя: выйдет «sittenoder». Отличает их
следующее слово: если это союз из списка (oder, und, bzw, sowie…), дефис
сохраняется.

Конец абзаца от переноса строки отличает длина: строка, которая заметно
короче остальных в этой карточке, кончает абзац (заголовок, конец мысли), и
перевод строки после неё остаётся.

Скрипт одноразовый и метит карточку ключом `text_reflowed`. Второй прогон по
собранному тексту НЕ безобиден: конец абзаца распознаётся по длине строки
относительно остальных в карточке, а в собранном тексте строка — это уже
целый абзац, и соседние абзацы склеиваются между собой. На Megarry & Wade
второй прогон менял текст у 714 карточек из 2929. Помеченные карточки
пропускаются; `--again` снимает защиту.

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


# Управляющие знаки из PDF: у Koziol в каждый узел иерархии затесался \x07
# («\x07Part\u2002 6 The elements of liability»), а типографские пробелы
# (en/em/тонкий/неразрывный) в поиске ведут себя не как пробел. Ни то ни
# другое не видно глазом в выдаче, но ломает и поиск, и сравнение строк.
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ODD_SPACE = re.compile(r"[\u00a0\u2000-\u200a\u202f\u205f\u3000]")


def clean_chars(s):
    return ODD_SPACE.sub(" ", CTRL.sub("", s))


def reflow(text, suspended, short_ratio=0.6):
    text = clean_chars(text)
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
        # Мягкий перенос U+00AD ставит только вёрстка и только по слогам:
        # висячим дефисом он не бывает никогда, поэтому склеивается без
        # оглядки на следующее слово. У Vansweevelt так набрано 1557 карточек
        # («achter\u00ad\nliggende»), и без этой ветки в тексте оставался
        # невидимый знак посреди слова.
        if prev.endswith("\u00ad"):
            out = prev[:-1] + stripped
            continue
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
    # Оставшиеся мягкие переносы — внутри строки — снимаются вместе с
    # пробелом, который мог оказаться следом: знака на экране не видно, а
    # слово он всё равно разрывает. Заодно скрипт остаётся идемпотентным —
    # текст, уже собранный прошлой версией, не рассыпается на «achter
    # liggende».
    out = re.sub("\u00ad\\s*", "", out)
    return re.sub(r" {2,}", " ", out).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--lang", default="en", choices=sorted(SUSPENDED))
    ap.add_argument("--short-ratio", type=float, default=0.6)
    ap.add_argument("--again", action="store_true",
                    help="прогнать заново по уже собранным карточкам (склеит абзацы — см. docstring)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    suspended = SUSPENDED[a.lang]
    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]
    changed = notes = heads = 0
    sample = None
    skipped = 0
    for c in cards:
        if c.get("text_reflowed") and not a.again:
            skipped += 1
            continue
        before = c.get("text") or ""
        after = reflow(before, suspended, a.short_ratio)
        if after != before:
            if sample is None:
                sample = (before[:220], after[:220])
            c["text"] = after
            changed += 1
        # Узлы иерархии — тот же набранный текст: у Vansweevelt в 30 из них
        # остался мягкий перенос, а показываются они в выдаче наравне с
        # цитатой.
        nodes = c.get("hierarchy") or []
        for k, node in enumerate(nodes):
            nn = reflow(node, suspended, a.short_ratio)
            if nn != node:
                nodes[k] = nn
                heads += 1
        c["text_reflowed"] = True
        for fn in c.get("footnotes") or []:
            t = fn.get("text") or ""
            nt = reflow(t, suspended, a.short_ratio)
            if nt != t:
                fn["text"] = nt
                notes += 1

    print(f"карточек перебрано: {changed} из {len(cards)}, сносок: {notes}, узлов иерархии: {heads}"
          + (f", пропущено как уже собранные: {skipped}" if skipped else ""))
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
