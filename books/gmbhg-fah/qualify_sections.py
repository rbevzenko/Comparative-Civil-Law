#!/usr/bin/env python3
"""Точный параграф и автор комментария в адресе карточки.

    python qualify_sections.py --book <каталог> [--dry-run]

Запускать после extract.py, ДО отчёта о качестве и выгрузки. Требует
work/headers.json — его готовит read_headers.py.

Чинит три вещи.

**Раздел берётся из колонтитула, а не из зашитого оглавления.** В оглавлении
файла узлов с параграфом 126 на 2000 полос, и два узла экскурса («§10 IPRG»,
«§12 IPRG») указывают на одну и ту же полосу — раздел по ним размазывается на
десятки полос. Колонтитул же стоит на каждой полосе тела (прочитан на 1990 из
2002) и называет параграф прямо.

**Граница параграфа проходит по строке, а не по полосе.** Комментарий к §15
кончается в середине той же полосы, где заголовком «§16. (1) …» начинается
следующий. Пока раздел переключался целой полосой, хвост предыдущего
параграфа получал чужой адрес и сталкивался по id с настоящими Rz следующего:
таких столкновений 74. Параграфы не выдумываются — их список берётся из
колонтитулов, а тело служит только чтобы найти, ГДЕ на полосе стоит заголовок.

**Автор параграфа входит в ссылку.** Издательство предписывает это прямо, на
обороте титула: «Kurzform: A.Winkler/M.Winkler in FAH, GmbHG §1». В томе 123
раздела и несколько десятков авторов; без имени ссылка на комментарий неполна,
а сослаться на «FAH, GmbHG §1» — всё равно что сослаться на сборник вместо
статьи.

Два экскурса — к международному корпоративному праву (§§ 10, 12 IPRG) и к
хозяйственному уголовному праву — идут со сквозной нумерацией Rz и получают
собственные адреса: их Rz 5 не имеет отношения к § 5 GmbHG.

**Иерархия строится по дереву оглавления, а не по номерам полос.** Узел
«V. Hauptstück. Behörden und Verfahren» в зашитом оглавлении указывает на
полосу 1338, хотя оба его параграфа (§102 и §104) стоят на 1880 и 1890:
ссылка в файле битая. Пайплайн же раскладывает узлы по полосам, и всё, что
между 1338 и 1892 — то есть §§72–107, четверть книги, — получало верхним
узлом «Behörden und Verfahren» вместо «Rechtsverhältnisse der Gesellschaft
und der Gesellschafter». Поэтому путь берётся из ДЕРЕВА: у параграфа он
складывается из заголовков его предков, и битая ссылка на полосу на него не
влияет.

**И последнее: аппарат параграфа переезжает в свой параграф.** Между последним
Rz одного параграфа и первым Rz следующего стоит аппарат следующего — текст
закона, справка о редакции, список Literatur. Своего номера у него нет, и
пайплайн приписывает его к последней карточке ПРЕДЫДУЩЕГО параграфа: у §81
Rz86 так набежало 23 тысячи знаков, почти целиком чужих.

Здесь такая карточка режется по заголовку следующего раздела, а снятый хвост
приписывается к его первой карточке. Просто выбросить было бы хуже: текст
закона — то, ради чего комментарий и открывают, и без него 89 полос книги
не попали бы в корпус вовсе. А под адресом «§ 82 Rz 1» он стоит там, где его
и станут искать.
"""

import argparse
import json
import os
import re
import sys

HEAD_EXKURS = re.compile(r"^Exkurs\s*:", re.I)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Заголовки в зашитом оглавлении набиты хвостами пробелов, а номер параграфа
# в них написан слитно («§31»). Postgres не примет управляющие символы в
# jsonb, а «§31» в иерархии просто читается хуже, чем «§ 31».
GLUED_SECTION = re.compile(r"^§\s*(\d)")
OUTLINE_SECTION = re.compile(r"^§\s*(\d[\d\s]*)\s*([a-z])?(?:[.\s]|$)")
EXKURS_IPRG = re.compile(r"Exkurs:\s*Internationales Gesellschaftsrecht", re.I)
EXKURS_WISTR = re.compile(r"Exkurs:\s*Wirtschaftsstrafrecht", re.I)


def tidy_node(text):
    out = CONTROL.sub("", text)
    out = GLUED_SECTION.sub(r"§ \1", out.strip())
    return re.sub(r"\s{2,}", " ", out).strip()


def outline_paths(pdf_path):
    """Раздел → путь по дереву оглавления (заголовки предков)."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    paths = {}

    def title_of(item):
        return CONTROL.sub("", str(getattr(item, "title", ""))).strip()

    def walk(node, path):
        prev = None
        for item in node:
            if isinstance(item, list):
                walk(item, path + ([prev] if prev else []))
                continue
            prev = title_of(item)
            if not prev:
                continue
            if EXKURS_IPRG.search(prev):
                paths.setdefault("Exkurs IPRG", path + [prev])
            elif EXKURS_WISTR.search(prev):
                paths.setdefault("Exkurs WiStR", path + [prev])
            m = OUTLINE_SECTION.match(prev)
            if m and "IPRG" not in prev:
                paths.setdefault(re.sub(r"\s+", "", m.group(1)) + (m.group(2) or ""), path)

    walk(reader.outline or [], [])
    return paths


def render_address(section, rz):
    if section == "Exkurs IPRG":
        return f"Exkurs §§ 10, 12 IPRG Rz {rz}"
    if section == "Exkurs WiStR":
        return f"Exkurs WiStR Rz {rz}"
    if "," in section or "–" in section:
        return f"§§ {section} Rz {rz}"
    return f"§ {section} Rz {rz}"


def key_of(section):
    return re.sub(r"[\s,]", "", section).replace("–", "-")


def cut_rx(section):
    """Заголовок раздела в НАЧАЛЕ строки — по нему режется хвост карточки."""
    if section.startswith("Exkurs"):
        return re.compile(r"(?m)^Exkurs\s*:")
    first = re.split(r"[,–]", section)[0].strip()
    return re.compile(rf"(?m)^§\s*{re.escape(first)}\.\s")


def heading_rx(section):
    """Как выглядит заголовок этого раздела в теле полосы."""
    if section.startswith("Exkurs"):
        return HEAD_EXKURS
    first = re.split(r"[,–]", section)[0].strip()
    return re.compile(rf"^§\s*{re.escape(first)}\.\s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True, help="исходный PDF — из него берётся дерево оглавления")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    hpath = os.path.join(a.book, "work", "headers.json")
    if not os.path.exists(hpath):
        sys.exit("нет work/headers.json — сначала read_headers.py")
    head = json.load(open(hpath, encoding="utf-8"))
    paths = outline_paths(a.pdf)
    authors = head["authors"]
    by_page = {int(k): v["section"] for k, v in head["pages"].items()}

    pages = {}
    for line in open(os.path.join(a.book, "work", "pages.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        pages[p["pdf_page"]] = p
    order = sorted(pages)

    # Полосы без колонтитула — это первые полосы разделов (шмуцтитул
    # Hauptstück, заголовок экскурса). Раздел у них тот же, что у следующей
    # полосы с колонтитулом.
    filled = 0
    for i, pno in enumerate(order):
        if pno in by_page:
            continue
        nxt = next((by_page[q] for q in order[i + 1:] if q in by_page), None)
        if nxt:
            by_page[pno] = nxt
            filled += 1
    print(f"полос: {len(order)}, раздел из колонтитула: {len(by_page) - filled}, "
          f"унаследован первой полосой раздела: {filled}")

    # Точки переключения: (полоса, доля высоты) → раздел.
    switches, by_page_only = [], []
    cur = None
    for pno in order:
        sec = by_page.get(pno)
        if sec is None or sec == cur:
            continue
        page = pages[pno]
        rx = heading_rx(sec)
        top = None
        for ln in page["lines"]:
            if rx.match(ln["text"].strip()):
                top = ln["top"] / (page["height"] or 1)
                break
        if top is None:
            top = 0.0
            by_page_only.append((pno, sec))
        switches.append((pno, top, sec))
        cur = sec
    print(f"разделов: {len(switches)}, из них заголовок в теле не найден: {len(by_page_only)}")
    for pno, sec in by_page_only[:8]:
        print(f"  f{pno}: {sec} — переключение по полосе")

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    def start_of(card):
        page = card.get("page_start")
        box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
        return (page, box["bbox"][1] if box else 0.0)

    seen, counts, moved, skipped, no_author = {}, {}, 0, 0, 0
    kept_old_path = 0
    for c in cards:
        pos = start_of(c)
        if pos[0] is None:
            skipped += 1
            continue
        hit = None
        for s in switches:
            if (s[0], s[1]) <= (pos[0], pos[1] + 1e-9):
                hit = s
            else:
                break
        if hit is None:
            skipped += 1
            continue
        sec = hit[2]
        if c.get("section") != sec:
            moved += 1
        rz = c["unit_number"]
        author = authors.get(sec)
        if not author:
            no_author += 1
        c["section"] = sec
        c["author"] = author
        c["address"] = render_address(sec, rz)
        c["citation"] = (f"{author} in FAH, GmbHG {c['address']}" if author
                         else f"FAH, GmbHG {c['address']}")
        c["external_id"] = f"{c['book_id']}:{c['unit_type'].lower()}:{key_of(sec)}/{rz}"
        c["id"] = f"{c['book_id']}-{c['unit_type'].lower()}{key_of(sec)}-{rz}"
        # Имя не `path`: ниже этим словом названа дорожка к cards.jsonl.
        branch = paths.get(sec) or paths.get(re.split(r"[,–]", sec)[0].strip())
        if branch is not None:
            c["hierarchy"] = [tidy_node(h) for h in branch] + ([] if sec.startswith("Exkurs")
                                                               else [f"§ {sec}"])
        else:
            c["hierarchy"] = [tidy_node(h) for h in (c.get("hierarchy") or [])]
            kept_old_path += 1
        counts[sec] = counts.get(sec, 0) + 1
        seen.setdefault(c["external_id"], []).append(c)

    # Хвост карточки за границей раздела — это аппарат следующего параграфа.
    trimmed, trim_chars, untrimmed = 0, 0, []
    # Позиции снимаются ОДИН раз, до правок: ниже у карточки-наследника
    # сдвигается page_start, и пересчитанная позиция поехала бы вслед за ним.
    pos_of = {id(c): start_of(c) for c in cards}
    ordered = sorted((c for c in cards if pos_of[id(c)][0] is not None),
                     key=lambda c: pos_of[id(c)])
    for i, c in enumerate(ordered):
        pos = pos_of[id(c)]
        # Карточка пересекает границу, если следующая карточка начинается уже
        # ЗА точкой переключения: аппарат следующего параграфа лежит между
        # ними, а значит внутри этой карточки. Одного page_end мало —
        # карточка может кончаться на той же полосе, но выше заголовка.
        nxt = next((s for s in switches if (s[0], s[1]) > (pos[0], pos[1] + 1e-9)), None)
        if nxt is None:
            continue
        after = pos_of[id(ordered[i + 1])] if i + 1 < len(ordered) else (10 ** 6, 0.0)
        if after <= (nxt[0], nxt[1]):
            continue
        # Заголовок ищется только в начале строки и только с точкой после
        # номера — перекрёстная ссылка так не выглядит («§2 Rz5», «§ 2 Abs 1»),
        # поэтому доля отрезаемого не ограничивается: у последней Rz параграфа
        # своего текста бывает одна строка, а чужого аппарата — две страницы.
        m = cut_rx(nxt[2]).search(c["text"])
        if not m or m.start() < 20:
            untrimmed.append((c["external_id"], nxt[2]))
            continue
        tail = c["text"][m.start():].strip()
        trim_chars += len(c["text"]) - m.start()
        c["text"] = c["text"][:m.start()].rstrip()
        c["page_end"] = nxt[0] if nxt[1] > 0.125 else nxt[0] - 1
        pp = pages.get(c["page_end"], {}).get("printed_page")
        if pp:
            c["printed_page_end"] = pp
        # Хвост — аппарат следующего параграфа; отдаём его первой карточке
        # этого параграфа вместе с полосами, на которых он стоит.
        heir = ordered[i + 1]
        heir["text"] = tail + "\n" + heir["text"]
        if heir.get("page_start") is None or nxt[0] < heir["page_start"]:
            heir["page_start"] = nxt[0]
            pp = pages.get(nxt[0], {}).get("printed_page")
            if pp:
                heir["printed_page_start"] = pp
        moved_chars = trim_chars
        trimmed += 1
    print(f"аппарат параграфа переехал в свой параграф: {trimmed} границ, знаков: {trim_chars}")
    if untrimmed:
        print(f"  не удалось найти заголовок для обрезки: {len(untrimmed)}")
        for eid, sec in untrimmed[:6]:
            print(f"    {eid} → {sec}")

    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print(f"\nкарточек с адресом: {sum(counts.values())}, без раздела: {skipped}, "
          f"переехало в другой параграф: {moved}, без автора: {no_author}")
    print(f"путь из дерева оглавления: {sum(counts.values()) - kept_old_path}, "
          f"оставлен прежний (раздела нет в оглавлении): {kept_old_path}")
    if dupes:
        print(f"ОСТАЛИСЬ СТОЛКНОВЕНИЯ id: {len(dupes)}")
        for k, v in list(dupes.items())[:8]:
            print(f"  {k}: полосы файла {[x.get('page_start') for x in v]}")
    else:
        print("столкновений id нет")

    if a.dry_run:
        for c in cards[:2] + cards[-2:]:
            print(f"  {c['external_id']:34s} | {c['citation']}")
        print("dry-run: файл не тронут")
        return

    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: qa_report.py")


if __name__ == "__main__":
    main()
