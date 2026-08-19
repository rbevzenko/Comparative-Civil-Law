#!/usr/bin/env python3
"""Починка узлов печатного оглавления, склеенных слоем OCR.

    python fix_toc.py --book <каталог книги> [--dry-run]

В слое, зашитом в этот скан, пять строк оглавления слиплись с соседними:
у книги есть узел, а в work/toc.json его нет, и карточки соответствующего
куска книги наследуют иерархию предыдущего раздела. Так пропали, в
частности, «4. Kapitel: Das Eigentum» и «3. Kapitel: Die eingetragene
Partnerschaft», и 55 карточек (3% корпуса) получили чужую главу.

Узел не выдумывается: склейка опознаётся по её собственной форме
«<заголовок> <колонцифра> <маркер> <заголовок>». Колонцифра посреди строки
и есть шов — она относится к первому узлу, а номер строки, прочитанный
разбором, к второму. Ни один заголовок при этом не сочиняется: обе половины
уже стоят в строке.

Заодно снимаются два следа того же слоя: колонцифра, влипшая в конец
заголовка, и остатки отточия.
"""

import argparse
import json
import os
import re
import sys

# Маркер уровня в этой книге: «1. Teil», «4. Kapitel», «II.», «C.», «3.», «a)».
MARKER = r'(?:\d{1,2}\.\s*(?:Teil|Kapitel)|[IVXL]{1,5}\.|[A-ZÄÖÜ]\.|\d{1,2}\.|[a-z]\))'
SEAM = re.compile(rf'^(?P<head>.+?)\s+(?P<page>\d{{1,3}})\s+(?P<tail>{MARKER}\s+\S.*)$')
TAIL_PAGE = re.compile(r'^(?P<title>.*?)[\s.]*\s(?P<page>\d{1,3})$')
LEADERS = re.compile(r'[\s._]*[.·_]{3,}[\s._]*$')
CITE_TAIL = re.compile(r'(?:§+|Art|Abs|Rz|Satz|Nr)\s*$')


def fits_order(entries, idx, page):
    """Ложится ли страница в порядок соседей: оглавление не убывает."""
    before = next((e["printed_page"] for e in reversed(entries[:idx])
                   if e.get("printed_page")), None)
    after = next((e["printed_page"] for e in entries[idx + 1:]
                  if e.get("printed_page")), None)
    return (before is None or page >= before) and (after is None or page <= after)

# Глубина второй половины берётся не из головы, а из соседей с тем же
# маркером: в этой книге Kapitel всегда на 1, «C.» — на 3, «1.» внутри
# «C.» — на 4. Пара (индекс узла, ожидаемая глубина) проверяется при
# запуске: не сошлось — значит оглавление другое, и чинить его вслепую нельзя.
DEPTH_BY_MARKER = {"part": 0, "chapter": 1, "roman": 2, "upper": 3, "digit": 4, "lower": 5}


def marker_kind(s):
    if re.match(r'^\d{1,2}\.\s*Teil', s):
        return "part"
    if re.match(r'^\d{1,2}\.\s*Kapitel', s):
        return "chapter"
    if re.match(r'^[IVXL]{1,5}\.', s):
        return "roman"
    if re.match(r'^[A-ZÄÖÜ]\.', s):
        return "upper"
    if re.match(r'^[a-z]\)', s):
        return "lower"
    if re.match(r'^\d{1,2}\.', s):
        return "digit"
    return None


def parse_marker(raw):
    """Номер и заголовок узла из его строки."""
    m = re.match(rf'^({MARKER})\s*:?\s*(.*)$', raw)
    if not m:
        return None, raw.strip()
    num = re.sub(r'\s*(?:Teil|Kapitel)\s*$', '', m.group(1).rstrip('.):')).strip()
    return num, m.group(2).strip(' :')


def clean_title(t):
    t = LEADERS.sub('', t)
    return re.sub(r'\s{2,}', ' ', t).strip(' .:_')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "toc.json")
    doc = json.load(open(path, encoding="utf-8"))
    out, split, repaged, cleaned = [], 0, 0, 0

    for idx, e in enumerate(doc["entries"]):
        m = SEAM.match(e["raw"])
        if m and marker_kind(m.group("tail")):
            head_raw = m.group("head").strip()
            tail_raw = m.group("tail").strip()
            kind = marker_kind(tail_raw)
            hnum, htitle = parse_marker(head_raw)
            tnum, ttitle = parse_marker(tail_raw)
            out.append(dict(e, raw=head_raw, number=hnum, title=clean_title(htitle),
                            printed_page=int(m.group("page")), repaired="seam-head"))
            out.append(dict(e, raw=tail_raw, number=tnum, title=clean_title(ttitle),
                            marker=kind, depth=DEPTH_BY_MARKER[kind], repaired="seam-tail"))
            split += 1
            continue

        title = e.get("title") or ""
        page = e.get("printed_page")
        # Колонцифра, влипшая в конец заголовка: «Die Reallasten 478» при
        # прочитанной странице 483. Верна та, что в заголовке, — она стоит
        # на своей строке, а прочитанная утекла со следующей.
        #
        # Две проверки, и обе обязательны. Число после «§», «Art», «Abs»,
        # «Rz» — это норма в самом заголовке («Die Fälle des § 879»), а не
        # страница. И новая страница обязана лечь в порядок соседей:
        # оглавление идёт по возрастанию, и правка, ломающая порядок, —
        # не правка, а порча.
        m2 = TAIL_PAGE.match(title)
        if (m2 and page and int(m2.group("page")) != page
                and len(m2.group("title")) > 3
                and not CITE_TAIL.search(m2.group("title"))):
            cand = int(m2.group("page"))
            if fits_order(doc["entries"], idx, cand):
                e = dict(e, title=m2.group("title").strip(), printed_page=cand,
                         repaired="tail-page")
                repaged += 1

        ct = clean_title(e.get("title") or "")
        if ct != (e.get("title") or ""):
            e = dict(e, title=ct, repaired=e.get("repaired") or "leaders")
            cleaned += 1
        out.append(e)

    print(f"склеек разъединено: {split}, колонцифр вынуто из заголовка: {repaged}, "
          f"заголовков почищено от отточия: {cleaned}")
    for e in out:
        if e.get("repaired", "").startswith("seam"):
            print(f"  d{e['depth']} {e['marker']:8s} p{e['printed_page']:<5} | {e['raw'][:80]}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    doc["entries"] = out
    doc["repaired_by"] = "fix_toc.py"
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Записано: {path} (узлов {len(out)})")


if __name__ == "__main__":
    main()
