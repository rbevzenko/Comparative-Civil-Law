#!/usr/bin/env python3
"""Дробление карточки-статьи DCFR/PEL на печатные части: правило, комментарии, заметки.

    python scripts/split_article_commentary.py --book books/<id> [--dry-run]
        [--heading-size 13.5] [--marker-style letters|cn]

Зачем. Единица цитирования у DCFR — статья, и это правильный адрес. Но у
полного издания комментарий к одной статье доходит до девяноста полос: в
томе DCFR две трети текста легли в карточки длиннее 18 000 знаков, а
эмбеддер видит только первые 18 000. То есть большая часть книги была бы
невидима для смыслового поиска, хотя формально лежала бы в корпусе.

Границы НЕ выдумываются. Берутся ровно те деления, что напечатаны в книге:

    COMMENTS                 служебный заголовок, отдельной строкой
    F. Approval by the …     буквенный подзаголовок комментария
    NOTES                    служебный заголовок, отдельной строкой
    21. In POLAND the …      нумерованная национальная заметка

Адрес ребёнка — тоже цитируемый: «II.–8:103, Comment F», «II.–8:103, Note 21».
Так DCFR и цитируют в литературе.

Помечают эти части по-разному, и стиль задаётся ключом `--marker-style`:

    letters  комментарий — буквенный подзаголовок «F. Approval by …»,
             заметка — номер «21. In POLAND …». Так набраны DCFR и серия PEL.
    cn       комментарий — «C4.», заметка — «N1.», прямо в начале абзаца.
             Так набран PEICL, и это не наша выдумка: собственный указатель
             книги ссылается ровно так — «Art. 1:101 C6», «Art. 2:202 N1».

При стиле `cn` кегль не проверяется: метка стоит в начале обычного абзаца
тем же кеглем, что и текст, и отличать её по типографике нечем — да и
незачем, буква «C» с цифрой сама по себе однозначна.

Буквенный подзаголовок опознаётся по КЕГЛЮ, а не по виду строки. В
иллюстрациях DCFR стороны названы буквами, и предложение начинается ровно
так же: «B. After 4 years A purports to terminate…». Отличить их по длине
строки или по точке в конце нельзя — а по кеглю можно: подзаголовок
набран 14 пунктами, тело 12. Набор заголовочных строк собирается из
work/pages.jsonl, и буква принимается, только если её строка там есть.

Номера заметок принимаются только по возрастанию внутри статьи. Иначе под
шаблон уйдут годы, номера статей национальных кодексов и перечисления
внутри абзаца — их в национальных заметках полно.

Страницы ребёнка считаются честно: карточка несёт char_start/char_end в
work/book.txt, а work/pagemap.json переводит диапазон знаков в полосы.
"""

import argparse
import bisect
import json
import os
import re

# Регистр служебного заголовка зависит от тома: главный набирает «COMMENTS»
# прописными, тома 5–6 — «Comments». Слово должно занимать всю строку:
# «Comments on paragraph (2)» — это уже текст, а не заголовок блока.
COMMENTS = re.compile(r"^COMMENTS\s*$|^Comments\s*$", re.M)
# «National Notes» — так этот блок назван в томах серии PEL; в DCFR он
# просто «NOTES». Слово должно занимать всю строку.
NOTES = re.compile(r"^NOTES\s*$|^(?:National\s+)?Notes\s*$", re.M)
# Буквенный подзаголовок: одна заглавная, точка, пробел, дальше текст.
# Строка короткая — это заголовок, а не абзац, начатый с инициала.
LETTER = re.compile(r"^([A-Z])\.\s+(\S[^\n]{0,90})$", re.M)
# Стиль PEICL: «C4. Two methods are apparent…», «N1. The full range…».
CN_COMMENT = re.compile(r"^C(\d{1,3})\.\s", re.M)
CN_NOTE = re.compile(r"^N(\d{1,3})\.\s", re.M)
# Нумерованная заметка: число, точка, пробел, дальше содержательный знак.
NOTE = re.compile(r"^(\d{1,3})\.\s+(?=[A-ZА-Я“‘\"(\[])", re.M)


def heading_lines(book, min_size):
    """Тексты строк, набранных заголовочным кеглем. Опора на типографику,
    а не на догадку по виду строки."""
    out = set()
    path = os.path.join(book, "work", "pages.jsonl")
    for line in open(path, encoding="utf-8"):
        for ln in json.loads(line)["lines"]:
            if (ln.get("size") or 0) >= min_size:
                t = ln["text"].strip()
                if t:
                    out.add(t)
    return out


def pages_for(pagemap, starts, a, b):
    """Полосы, на которые попадает диапазон знаков [a, b)."""
    i = max(0, bisect.bisect_right(starts, a) - 1)
    j = max(i, bisect.bisect_right(starts, max(a, b - 1)) - 1)
    return pagemap[i], pagemap[j]


def cut_points(text, rx, monotonic=False, headings=None):
    """Позиции начала кусков по шаблону. monotonic — только растущие номера.
    headings — если задан, строка должна быть набрана заголовочным кеглем."""
    out, last = [], 0
    for m in rx.finditer(text):
        if headings is not None:
            eol = text.find("\n", m.start())
            line = text[m.start():eol if eol != -1 else len(text)].strip()
            if line not in headings:
                continue
        if monotonic:
            n = int(m.group(1))
            # Не просто «больше предыдущего», а «следом за ним», с
            # небольшим допуском. Голого возрастания мало: в национальных
            # заметках полно чисел, начинающих строку, — номера статей
            # чужих кодексов, годы, страницы. Так в заметках к II.–1:104
            # после номера 20 принималось «114», и ряд получал дыру в
            # девяносто три номера на ровном месте. Число, не подошедшее
            # под ряд, остаётся текстом соседней заметки: потерять кусок
            # текста хуже, чем потерять границу между двумя заметками.
            if not (last < n <= last + 3):
                continue
            last = n
        out.append((m.start(), m.group(1)))
    return out


def split_block(text, base, rx, kind, monotonic, headings=None):
    """Блок → список (метка, начало, конец) по печатным делениям."""
    pts = cut_points(text, rx, monotonic, headings)
    if not pts:
        return [(None, base, base + len(text))]
    parts = []
    if pts[0][0] > 0:
        parts.append((None, base, base + pts[0][0]))
    for k, (pos, label) in enumerate(pts):
        end = pts[k + 1][0] if k + 1 < len(pts) else len(text)
        parts.append((label, base + pos, base + end))
    return parts


def split_card(card, pagemap, starts, headings=None, style="letters"):
    text = card["text"]
    mc, mn = COMMENTS.search(text), NOTES.search(text)
    # Заметки идут после комментариев; если порядок нарушен, метка ложная.
    if mc and mn and mn.start() < mc.start():
        mn = None

    segments = []          # (unit_type, label, start, end)
    head_end = mc.start() if mc else (mn.start() if mn else len(text))
    segments.append(("Art.", None, 0, head_end))

    if mc:
        cend = mn.start() if mn else len(text)
        body = text[mc.end():cend]
        crx = CN_COMMENT if style == "cn" else LETTER
        cheads = None if style == "cn" else headings
        for label, a, b in split_block(body, mc.end(), crx, "Comment", style == "cn", cheads):
            segments.append(("Comment", label, a, b))
    if mn:
        body = text[mn.end():]
        nrx = CN_NOTE if style == "cn" else NOTE
        for label, a, b in split_block(body, mn.end(), nrx, "Note", True):
            segments.append(("Note", label, a, b))

    out = []
    for kind, label, a, b in segments:
        chunk = text[a:b].strip()
        if not chunk:
            continue
        if kind == "Art.":
            ext, addr, num = card["external_id"], card["address"], card["unit_number"]
        elif kind == "Comment":
            suffix = label or "x"
            ext = f"{card['external_id']}#c{suffix}"
            if not label:
                addr = f"{card['address']}, Comments"
            elif style == "cn":
                addr = f"{card['address']} C{label}"
            else:
                addr = f"{card['address']}, Comment {label}"
            num = label or ""
        else:
            suffix = label or "x"
            ext = f"{card['external_id']}#n{suffix}"
            if not label:
                addr = f"{card['address']}, Notes"
            elif style == "cn":
                addr = f"{card['address']} N{label}"
            else:
                addr = f"{card['address']}, Note {label}"
            num = label or ""
        # Числовое поле — своё, а не родительское. Отчёт о качестве считает
        # непрерывность по нему, и с унаследованным номером статьи все
        # заметки одной статьи выглядели бы дублями одного номера.
        if kind == "Art.":
            number = card.get("number")
        elif kind == "Note":
            number = int(label) if label and label.isdigit() else None
        elif style == "cn":
            number = int(label) if label and label.isdigit() else None
        else:
            # Буква комментария как порядковый номер: A→1, B→2. Ряд
            # осмысленный, дыра в нём — настоящая дыра.
            number = (ord(label) - 64) if label and len(label) == 1 and label.isalpha() else None
        cs = card["char_start"] + a
        ce = card["char_start"] + b
        p1, p2 = pages_for(pagemap, starts, cs, ce)
        kid = dict(card)
        kid.update({
            # У ребёнка РАЗДЕЛ — сама статья, а не глава. Нумерация
            # комментариев и заметок перезапускается в каждой статье, и
            # если оставить разделом главу, ряды всех статей главы
            # сольются: отчёт о качестве насчитает тысячи мнимых дублей
            # и дыр там, где нумерация в порядке.
            "section": card["address"] if kind != "Art." else card.get("section"),
            "external_id": ext,
            "id": ext.replace(":", "-").replace("/", "-"),
            "unit": kind, "unit_type": kind, "unit_number": str(num), "number": number,
            "address": addr,
            "citation": card["citation"].replace(card["address"], addr),
            "text": chunk,
            "char_start": cs, "char_end": ce,
            "page_start": p1["pdf_page"], "page_end": p2["pdf_page"],
            "printed_page_start": p1.get("printed_page"), "printed_page_end": p2.get("printed_page"),
            "split_from": card["external_id"],
        })
        kid.pop("bbox", None)      # рамки родителя ребёнку не годятся
        out.append(kid)
    return out


def mark_repeats(cards):
    """Повторившийся адрес помечается номером ряда: «Comment C (2)».

    Повторы настоящие, а не наши. Во-первых, у части статей буквенный ряд
    комментариев начинается заново — обычно там, где комментарии идут по
    пунктам статьи и к каждому пункту свой ряд A, B, C. Во-вторых, две
    статьи (VIII.–4:102 и IX.–6:102) напечатаны в томе дважды.

    Молча склеивать такие карточки нельзя — это разный текст. Выкидывать
    вторую тоже нельзя. Поэтому адрес сохраняется как напечатан, а к нему
    добавляется номер повтора: видно и то, что напечатано, и то, что это
    второе вхождение.
    """
    seen = {}
    for c in cards:
        n = seen.get(c["address"], 0) + 1
        seen[c["address"]] = n
        if n > 1:
            old = c["address"]
            c["address"] = f"{old} ({n})"
            c["citation"] = c["citation"].replace(old, c["address"])
            c["external_id"] = f"{c['external_id']}~{n}"
            c["id"] = c["external_id"].replace(":", "-").replace("/", "-")
            c["repeat_of"] = old
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--marker-style", choices=("letters", "cn"), default="letters",
                    help="чем помечены части статьи: буквой (DCFR, PEL) или C/N (PEICL)")
    ap.add_argument("--heading-size", type=float, default=13.5,
                    help="кегль, с которого строка считается подзаголовком комментария")
    a = ap.parse_args()

    cards_path = os.path.join(a.book, "output", "cards.jsonl")
    pagemap = json.load(open(os.path.join(a.book, "work", "pagemap.json"), encoding="utf-8"))
    starts = [p["start"] for p in pagemap]
    cards = [json.loads(l) for l in open(cards_path, encoding="utf-8") if l.strip()]
    headings = heading_lines(a.book, a.heading_size)
    print(f"строк заголовочного кегля (>= {a.heading_size}): {len(headings)}")

    out = []
    for c in cards:
        out.extend(split_card(c, pagemap, starts, headings, a.marker_style))

    out = mark_repeats(out)
    ids = [c["external_id"] for c in out]
    dup = len(ids) - len(set(ids))
    lens = sorted(len(c["text"]) for c in out)
    over = sum(1 for x in lens if x > 18000)
    print(f"было карточек: {len(cards)}, стало: {len(out)}")
    print(f"медиана {lens[len(lens)//2]} знаков, длиннее 18000: {over}, максимум {lens[-1]}")
    if dup:
        raise SystemExit(f"совпавших external_id: {dup} — дробление не применено")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(cards_path, "w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"записано: {cards_path}")


if __name__ == "__main__":
    main()
