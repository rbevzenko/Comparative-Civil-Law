#!/usr/bin/env python3
"""Сноски по КЛИКАБЕЛЬНЫМ ссылкам: знак в теле → полоса с текстом сноски.

    python scripts/footnotes_from_links.py --book books/<id> --pdf книга.pdf \
        [--body-min-chars 1200] [--marker-size-max 8] [--drop-note-pages] [--dry-run]

Запускать МЕЖДУ pages_digital.py и extract.py: сноски дописываются в модель
полосы (`work/pages.jsonl`), и дальше сборка идёт обычным порядком.

ЗАЧЕМ. У французских электронных изданий (Dalloz, LGDJ через Numilog) сноски
вынесены на ОТДЕЛЬНЫЕ полосы файла — по одной сноске на полосу. У Флура на
книгу в семьсот печатных страниц приходится 7844 полосы файла, и почти все
они заняты аппаратом. Резать такой файл «как обычно» значит выбросить весь
аппарат, а во французской книге именно в нём лежат реквизиты решений
Кассационного суда.

ПОЛОСЫ ЭТИ ПЕРЕМЕЖАЮТСЯ С ТЕЛОМ, а не лежат блоком в конце: у Терре по
обязательствам полоса 2908 — тело, а соседняя 2000 — сноска. Диапазоном их
не отсечь.

Делятся они в два прохода, и одного объёма текста для этого мало. Сначала
берутся полосы заведомо крупные (порог `--body-min-chars`) — это опора.
Дальше полосой со сноской считается только та, НА КОТОРУЮ С ОПОРНЫХ ПОЛОС
ВЕДЁТ ССЫЛКА со знаком сноски. Всё остальное остаётся телом.

Порядок именно такой, потому что короткая полоса — не обязательно сноска:
конец главы, полоса с одним заголовком, врезка. У Реми-Кабрийака таких
пограничных полос (от 300 до 1200 знаков) триста пятьдесят пять, и рубить
их по объёму значило бы выбросить куски книги.

Отделять сноски по кеглю или по низу полосы здесь нечем: они не внизу
полосы, а на другой полосе. Зато связь лежит прямо в файле: от надстрочного
номера идёт ссылка-аннотация на нужную полосу. Скилл называет этот случай
лучшим и оставляет режим `links` нереализованным (см. бэклог) — это его
реализация.

КАК ЧИТАЕТСЯ НОМЕР. Не из текста ссылки, а из текста ПОД её прямоугольником:
у аннотации есть Rect, и надстрочный номер сидит ровно в нём. Так надёжнее,
чем брать первое число строки: в тексте полно номеров статей и годов.

ПОРОГ КЕГЛЯ СЧИТАЕТСЯ, А НЕ ЗАДАЁТСЯ. Знак сноски мельче тела, но насколько
— зависит от издания: у Реми-Кабрийака тело 15.0, а знак 11.2; фиксированные
восемь пунктов из первой версии отсекали знак вместе с телом, и привязалось
ноль сносок из полутора тысяч. Поэтому порог берётся как доля от самого
частого кегля НА ЭТОЙ полосе.

АДРЕСА ССЫЛОК В ФАЙЛЕ БЫВАЮТ БИТЫЕ, и слепо им верить нельзя. У
Реми-Кабрийака со знака 757 на полосе 204 ссылка ведёт на полосу 201, где
лежит чистое тело — три абзаца книги подряд. Полоса при этом уходила в
сноски и выбрасывалась вместе с абзацами 222–224.

Защита простая и не требует знать профиль: полоса, на которой есть строки
с НОМЕРОМ АБЗАЦА (число, пробел, заглавная буква), — это тело, и сноской
она не объявляется, куда бы ни вела ссылка. У настоящей полосы со сноской
таких строк нет: там сразу текст примечания.

ЧЕГО СКРИПТ НЕ ДЕЛАЕТ. Не переносит сноску в тело и не удаляет её знак:
знак остаётся в тексте карточки, как он стоит в книге.
"""

import argparse
import json
import os
import re
from collections import defaultdict


def link_targets(reader, page_index):
    """Ссылки полосы: [(прямоугольник, номер целевой полосы)]."""
    out = []
    page = reader.pages[page_index]
    for a in (page.get("/Annots") or []):
        try:
            o = a.get_object()
            if o.get("/Subtype") != "/Link":
                continue
            dest = o.get("/Dest")
            if dest is None:
                continue
            first = dest[0] if isinstance(dest, list) else None
            if first is None or not hasattr(first, "get_object"):
                continue
            tgt = reader.get_page_number(first.get_object())
            rect = [float(x) for x in o["/Rect"]]
            out.append((rect, tgt))
        except Exception:
            continue
    return out


def marker_at(chars, rect, height, pad=1.5):
    """Текст под прямоугольником ссылки — это и есть знак сноски.

    Координаты аннотации отсчитываются снизу, координаты символов —
    сверху; отсюда пересчёт по высоте полосы.
    """
    x0, y0, x1, y1 = rect
    top, bottom = height - y1, height - y0
    got = [c for c in chars
           if c["x0"] >= x0 - pad and c["x1"] <= x1 + pad
           and c["top"] >= top - pad and c["bottom"] <= bottom + pad]
    got.sort(key=lambda c: c["x0"])
    return "".join(c["text"] for c in got).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--body-min-chars", type=int, default=1200,
                    help="знаков на полосе, начиная с которых она считается телом")
    ap.add_argument("--unit-marker",
                    default=r"^\d{1,4}\s+[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]",
                    help="признак строки с номером единицы; полоса с такими строками "
                         "считается телом и в сноски не уходит")
    ap.add_argument("--drop-note-pages", action="store_true",
                    help="убрать полосы-сноски из модели после привязки")
    ap.add_argument("--marker-size-max", type=float,
                    help="кегль, выше которого совпадение знаком сноски не считается; "
                         "по умолчанию считается от кегля тела полосы")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pdfplumber
    from pypdf import PdfReader

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    in_model = {p["pdf_page"] for p in pages}
    chars_of = {p["pdf_page"]: sum(len(l["text"]) for l in p["lines"]) for p in pages}
    seed = {p for p, c in chars_of.items() if c >= a.body_min_chars}
    print(f"полос в модели: {len(in_model)}, опорных полос тела: {len(seed)}")

    unit_rx = re.compile(a.unit_marker)
    # Полосы, на которых стоят номера абзацев, — тело. Считается по модели,
    # то есть по уже разобранным строкам, а не по сырому тексту.
    # Строк с номером должно быть НЕ МЕНЬШЕ ДВУХ. Одной мало: сноска сама
    # часто начинается с числа («1376 C. civ. », RTD civ. 1989…»), и по одной
    # строке полоса со сноской выдаёт себя за тело. У настоящей полосы тела
    # номеров абзацев несколько.
    has_unit = {p["pdf_page"] for p in pages
                if sum(1 for l in p["lines"] if unit_rx.match(l["text"].strip())) >= 2}
    print(f"полос с номерами абзацев: {len(has_unit)}")

    reader = PdfReader(a.pdf)
    notes_by_page = defaultdict(list)
    targets = set()
    no_marker = bad_number = 0

    with pdfplumber.open(a.pdf) as pdf:
        for p in sorted(seed):
            chars = pdf.pages[p - 1].chars
            height = pdf.pages[p - 1].height
            if a.marker_size_max is not None:
                cap = a.marker_size_max
            else:
                sizes = [round(c["size"], 1) for c in chars if c.get("size")]
                body_size = max(set(sizes), key=sizes.count) if sizes else 0
                cap = body_size * 0.92
            small = [c for c in chars if (c.get("size") or 99) <= cap]
            for rect, tgt in link_targets(reader, p - 1):
                if (tgt + 1) in seed or (tgt + 1) in has_unit:
                    continue   # цель — тело: перекрёстная ссылка либо битый адрес
                mark = marker_at(small, rect, height)
                m = re.search(r"\d{1,4}", mark)
                if not m:
                    no_marker += 1
                    continue
                targets.add(tgt)
                notes_by_page[p].append((int(m.group()), tgt))

        # текст сносок берётся один раз на каждую целевую полосу
        text_of = {}
        for tgt in sorted(targets):
            t = (pdf.pages[tgt].extract_text() or "").strip()
            text_of[tgt] = re.sub(r"\s*\n\s*", " ", t)

    attached = 0
    for pg in pages:
        got = notes_by_page.get(pg["pdf_page"])
        if not got:
            continue
        seen, notes = set(), []
        for num, tgt in got:
            if num in seen:
                continue
            seen.add(num)
            txt = text_of.get(tgt, "")
            if not txt:
                bad_number += 1
                continue
            # Страница у сноски не может быть пустой: сборщик сортирует по
            # ней вместе с номером и на None падает. Если колонцифра не
            # прочиталась, берётся полоса файла — она есть всегда.
            notes.append({"number": num, "text": txt,
                          "page": pg.get("printed_page") or pg["pdf_page"]})
        if notes:
            pg["notes"] = (pg.get("notes") or []) + notes
            attached += len(notes)

    print(f"полос-сносок задействовано: {len(targets)}")
    print(f"сносок привязано: {attached}; знак не прочитан у {no_marker}; пустой текст у {bad_number}")
    note_pages = {t + 1 for t in targets}
    body = in_model - note_pages
    print(f"полос тела: {len(body)}, полос со сносками: {len(note_pages)}")

    if a.drop_note_pages:
        keep = [p for p in pages if p["pdf_page"] in body]
        print(f"полос-сносок убрано из модели: {len(pages) - len(keep)}")
        pages = keep

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
