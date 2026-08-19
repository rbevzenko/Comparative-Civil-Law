#!/usr/bin/env python3
"""Точный § и код акта в адресе карточки.

    python qualify_sections.py --book <каталог> --pdf <файл> [--dry-run]

Запускать сразу после extract.py, ДО отчёта о качестве и выгрузки. Чинит две
вещи, каждая из которых по отдельности ломает ссылку.

**Граница параграфа проходит по строке, а не по странице.** Пайплайн в режиме
`section: outline` переключает § на всю страницу, где стоит узел оглавления.
Но комментарий к § 1 кончается в середине той же полосы, где начинается § 2:
на f83 сверху идут Rz 42 и 43 из § 1, а ниже — заголовок «§ 2. (1) Die
Rechtswirkungen …». Из-за этого хвост предыдущего параграфа получает чужой
адрес и сталкивается по id с настоящими Rz 42-43 параграфа 2 — таких
столкновений в томе 846.

Параграфы не выдумываются: их список берётся из зашитого в файл оглавления
(442 узла), а тело используется только чтобы найти, где именно на странице
стоит заголовок нужного параграфа. Не нашёлся — переключаемся по странице,
как раньше, и это видно в отчёте.

**Код акта входит в адрес.** Том комментирует четыре акта — IO, ReO, EKEG и
EuInsVO, — и номера параграфов между ними повторяются: «§ 1» есть в трёх из
них. Границы актов берутся из узлов верхнего уровня того же оглавления.
Оформление — по конвенции самой книги, она видна в колонтитуле: у IO код не
пишется («§3 Kodek»), у остальных пишется после номера («§7 ReO Reisch»,
«Art45 EuInsVO Weber-Wilfert»).
"""

import argparse
import json
import os
import re
import sys

LAWS = [
    ("IO", re.compile(r"Insolvenzordnung\s*[–-]\s*IO|\(Insolvenzordnung", re.I)),
    ("ReO", re.compile(r"Restrukturierungsordnung|\bReO\b")),
    ("EKEG", re.compile(r"\bEKEG\b")),
    ("EuInsVO", re.compile(r"\bEuInsVO\b")),
]
SECTION = re.compile(r"(?:§|Artikel)\s*(\d+[a-z]?)")
# «Vor § 1 …» — вводный комментарий перед параграфом, самостоятельная единица
# цитирования со своей нумерацией Rz. Без отдельного адреса он сталкивается
# с настоящим § 1: у EKEG это ровно так и происходит.
BEFORE = re.compile(r"^Vor\s*§\s*(\d+[a-z]?)", re.I)
# Заголовки в оглавлении этого файла набиты хвостами \x00. В карточку они
# попадают через иерархию, а Postgres такого в jsonb не принимает и отвечает
# голой 500 — чистим здесь, пока карточка ещё своя.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def read_outline(pdf_path):
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    flat = []

    def walk(node, depth=0):
        for item in node:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                try:
                    page = reader.get_destination_page_number(item) + 1
                except Exception:
                    continue
                flat.append({"page": page, "depth": depth,
                             "title": str(getattr(item, "title", "")).strip()})

    walk(reader.outline or [])
    flat.sort(key=lambda e: (e["page"], e["depth"]))
    return flat


def law_ranges(flat, body_end):
    """Диапазоны актов по узлам верхнего уровня; всё после тела отбрасывается."""
    tops = [e for e in flat if e["depth"] == 0 and e["page"] <= body_end]
    out = []
    for i, e in enumerate(tops):
        code = next((c for c, rx in LAWS if rx.search(e["title"])), None)
        if code is None:
            continue
        end = tops[i + 1]["page"] - 1 if i + 1 < len(tops) else body_end
        out.append((e["page"], end, code))
    return out


def heading_top(page, number, before=False):
    """Где на полосе стоит заголовок этого параграфа."""
    if before:
        rx = re.compile(rf"^Vor\s*§\s*{re.escape(number)}\b", re.I)
    else:
        rx = re.compile(rf"^(?:§\s*{re.escape(number)}\.|Artikel\s+{re.escape(number)}\b)")
    for ln in page["lines"]:
        if rx.match(ln["text"].strip()):
            return ln["top"] / (page["height"] or 1)
    return None


def render(code, number, unit_type, rz, before=False):
    if before:
        head = f"Vor § {number}" if code == "IO" else f"Vor § {number} {code}"
    elif code == "EuInsVO":
        head = f"Art {number} {code}"
    else:
        head = f"§ {number}" if code == "IO" else f"§ {number} {code}"
    return f"{head} {unit_type} {rz}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--body-end", type=int, default=3629)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pages = {}
    for line in open(os.path.join(a.book, "work", "pages.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        pages[p["pdf_page"]] = p

    flat = read_outline(a.pdf)
    ranges = law_ranges(flat, a.body_end)
    if not ranges:
        sys.exit("в оглавлении файла не нашлось узлов с кодами актов")
    print("диапазоны актов из оглавления:")
    for lo, hi, code in ranges:
        print(f"  {code:8s} f{lo}–{hi}")

    def law_of(page):
        return next((c for lo, hi, c in ranges if lo <= page <= hi), None)

    # Точки переключения параграфа: (страница, доля высоты полосы) → § и акт.
    switches, by_page_only = [], 0
    for e in flat:
        if e["depth"] == 0 or e["page"] > a.body_end:
            continue
        pre = BEFORE.match(e["title"])
        m = pre or SECTION.search(e["title"])
        if not m:
            continue
        page = pages.get(e["page"])
        top = heading_top(page, m.group(1), bool(pre)) if page else None
        if top is None:
            top = 0.0
            by_page_only += 1
        switches.append((e["page"], top, m.group(1), law_of(e["page"]), bool(pre)))
    switches.sort(key=lambda s: (s[0], s[1]))
    print(f"\nпараграфов из оглавления: {len(switches)}, "
          f"из них заголовок в теле не найден: {by_page_only}")

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    def start_of(card):
        page = card.get("page_start")
        box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
        return (page, box["bbox"][1] if box else 0.0)

    seen, counts, moved, skipped = {}, {}, 0, 0
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
        if hit is None or hit[3] is None:
            skipped += 1
            continue
        _, _, num, code, pre = hit
        if c.get("section") != num:
            moved += 1
        rz = c["unit_number"]
        key = f"{'Vor' if pre else ''}{code}{num}"
        c["law"] = code
        c["section"] = f"{'Vor ' if pre else ''}{code} {num}"
        c["address"] = render(code, num, c["unit_type"], rz, pre)
        c["citation"] = f"{c['citation'].split(' §')[0].split(' Art ')[0].split(' Vor ')[0]} {c['address']}"
        c["external_id"] = f"{c['book_id']}:{c['unit_type'].lower()}:{key}/{rz}"
        c["id"] = f"{c['book_id']}-{c['unit_type'].lower()}{key}-{rz}"
        c["hierarchy"] = [CONTROL.sub("", h).strip() for h in (c.get("hierarchy") or [])]
        counts[code] = counts.get(code, 0) + 1
        seen.setdefault(c["external_id"], []).append(c)

    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print(f"\nкарточек с адресом: {sum(counts.values())}, без раздела: {skipped}, "
          f"переехало в другой параграф: {moved}")
    for code in sorted(counts):
        print(f"  {code:8s} {counts[code]}")
    if dupes:
        print(f"\nОСТАЛИСЬ СТОЛКНОВЕНИЯ id: {len(dupes)}")
        for k, v in list(dupes.items())[:8]:
            print(f"  {k}: страницы файла {[x.get('page_start') for x in v]}")
    else:
        print("\nстолкновений id нет")

    if a.dry_run:
        for c in cards[:2] + cards[-2:]:
            if c.get("law"):
                print(f"  {c['external_id']:44s} | {c['citation']}")
        print("dry-run: файл не тронут")
        return

    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: qa_report.py")


if __name__ == "__main__":
    main()
