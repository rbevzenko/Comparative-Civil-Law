#!/usr/bin/env python3
"""Параграф из колонтитула и комментатор из подвала — прямо из PDF.

    python scripts/section_from_page_head.py --book books/<id> --pdf книга.pdf \
        --head-pattern '§\\s*(\\d+[a-zä]?)' --foot-pattern '^([A-ZÄÖÜ][\\w/.-]+)\\s+\\d{1,4}$' \
        --address '§ {section} Rdn. {number}' \
        --citation 'Stein/Jonas/{bearbeiter}, ZPO, 23. Aufl., {address}' [--dry-run]

Запускать ПОСЛЕ extract.py, ДО qa_report.py.

ЗАЧЕМ. У Großkommentare der Praxis (Stein/Jonas к ГПК, Jaeger к InsO) в теле
полосы параграфа нет вовсе: он стоит в колонтитуле («§ 4 | Erstes Buch –
Allgemeine Vorschriften»), а внизу, рядом с колонцифрой, — фамилия
комментатора этого параграфа («Kruis 88»). Без параграфа «Rdn. 164» не адрес:
в томе таких номеров девять штук. Без комментатора не собрать ссылку: у
большого комментария она всегда «Stein/Jonas/Kruis», а не «Stein/Jonas».

`hierarchy_from_running_head.py` сюда не годится: он кладёт колонтитул целиком
в иерархию и по дороге снимает ведущее число, принимая его за колонцифру, —
от «§ 4 | Erstes Buch» остаётся «| Erstes Buch».

Обе строки читаются из PDF по полосам сверху и снизу и переносятся вперёд:
на полосе без колонтитула (первая полоса параграфа, шмуцтитул) действует
последнее прочитанное значение.
"""

import argparse
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--head-pattern", default=r"§\s*(\d+[a-zä]?)")
    ap.add_argument("--foot-pattern", default=r"^([A-ZÄÖÜ][A-Za-zÄÖÜäöüß/.\-]+(?:\s[A-ZÄÖÜ][A-Za-zÄÖÜäöüß/.\-]+)?)\s+\d{1,4}$")
    ap.add_argument("--head-band", type=float, default=0.06)
    ap.add_argument("--foot-band", type=float, default=0.09)
    ap.add_argument("--address", default="{section} Rdn. {number}")
    ap.add_argument("--citation", required=True)
    ap.add_argument("--only-missing", action="store_true",
                    help="параграф ставить только там, где его нет: обычно он уже\n                          снят по заголовку в теле, а колонтитул — запасной путь")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = P.book_dirs(a.book)
    cards = P.read_jsonl(os.path.join(d["output"], "cards.jsonl"))
    if not cards:
        sys.exit("нет карточек")
    book_id = cards[0]["book_id"]
    pages = sorted({c["page_start"] for c in cards} | {c["page_end"] for c in cards})

    head_rx, foot_rx = re.compile(a.head_pattern), re.compile(a.foot_pattern)
    sec_by_page, who_by_page = {}, {}
    with pdfplumber.open(a.pdf) as pdf:
        for pno in pages:
            if pno > len(pdf.pages):
                continue
            page = pdf.pages[pno - 1]
            h = float(page.height)
            for ln in P.chars_to_lines(page.chars):
                t = re.sub(r"\s+", " ", ln["text"]).strip()
                if not t:
                    continue
                if ln["top"] <= h * a.head_band:
                    m = head_rx.search(t)
                    if m:
                        # Групп в образце может быть несколько: у тома есть и
                        # параграфы, и Einleitung без номера вовсе.
                        val = next((g for g in m.groups() if g), None)
                        if val:
                            sec_by_page[pno] = val
                elif ln["bottom"] >= h * (1 - a.foot_band):
                    m = foot_rx.match(t)
                    if m:
                        who_by_page[pno] = m.group(1)
            page.flush_cache()
            page.get_textmap.cache_clear()

    sec, who = None, None
    fill_sec, fill_who = {}, {}
    for pno in pages:
        sec = sec_by_page.get(pno, sec)
        who = who_by_page.get(pno, who)
        fill_sec[pno], fill_who[pno] = sec, who

    changed = 0
    for c in cards:
        s = c.get("section") if (a.only_missing and c.get("section")) else fill_sec.get(c["page_start"])
        w = fill_who.get(c["page_start"]) or ""
        if not s:
            continue
        # У параграфа адрес начинается со знака §, у Einleitung и Vorbemerkungen
        # его нет вовсе: «§ Einleitung Rdn. 1» — не адрес, а нелепость.
        label = f"§ {s}" if re.match(r"^\d", s) else s
        address = a.address.format(section=label, number=c["number"], unit_type=c["unit_type"])
        c["section"] = s
        c["address"] = address
        c["citation"] = re.sub(r"\s+", " ", a.citation.format(
            bearbeiter=w, section=s, number=c["number"], address=address)).replace("/,", ",").strip()
        c["external_id"] = f"{book_id}:{c['external_id'].split(':')[1]}:{s}/{c['number']}"
        c["hierarchy"] = [f"§ {s}"] + [x for x in (c.get("hierarchy") or []) if not x.startswith("§")]
        changed += 1

    print(f"полос с параграфом в колонтитуле: {len(sec_by_page)} из {len(pages)}")
    print(f"полос с фамилией в подвале: {len(who_by_page)}")
    print(f"карточек с проставленным параграфом: {changed} из {len(cards)}")
    ids = [c["external_id"] for c in cards]
    print(f"дублей адреса после правки: {len(ids) - len(set(ids))}")
    for c in cards[:2]:
        print(f'  пример: {c["external_id"]} → {c["citation"]}')
    if not a.dry_run:
        P.write_jsonl(os.path.join(d["output"], "cards.jsonl"), cards)
        print("карточки переписаны")


if __name__ == "__main__":
    main()
