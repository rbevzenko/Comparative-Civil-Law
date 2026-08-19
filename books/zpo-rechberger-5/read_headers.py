#!/usr/bin/env python3
"""Колонтитул каждой полосы → work/headers.json.

    python read_headers.py --pdf <файл> --book <каталог> [--pages 44-2216]

Запускать после pages_digital.py: тот снимает колонтитул как шум, а в нём
стоят обе вещи, которых больше взять негде.

Первая — номер параграфа. В зашитом оглавлении узлов всего 86 на две с
лишним тысячи полос, и это Teile и Titel, а не параграфы. Колонтитул же
называет параграф на каждой полосе тела.

Вторая — автор комментария. Издательство предписывает его в ссылке прямо на
обороте титула: «Gitschthaler in Rechberger/Klicka, ZPO5 §132 Rz1».

Колонтитул печатается зеркально, и стороны несут разное:

    verso   «§52 Fucik»                    — параграф и автор
    recto   «Zuständigkeit JN § 28»        — рубрика, код акта и параграф

Автор — это то, что стоит ПОСЛЕ номера; рубрика — то, что до него. По этому
признаку они и различаются, а не по чётности полосы: чётность у книги своя, а
правило «после номера — автор» держится на обеих сторонах разворота.

Карта «раздел → автор» здесь НЕ строится намеренно. Одного номера параграфа
для неё мало: том комментирует четыре акта, и «§ 1» есть и в JN (Mayr), и в
ZPO (Fucik). Ключ должен быть парой (акт, параграф), а акт виден только по
диапазону полос — его знает qualify_sections.py, он карту и складывает.
"""

import argparse
import json
import os
import re

# Порядок важен: «Vor § 1» и «Nach § 27a» разбираются до одиночного «§ 1» —
# это самостоятельные блоки комментария со своей нумерацией Rz, и без
# отдельного адреса они сталкиваются с самим параграфом.
#
# Номер набирается так: цифры, между которыми pypdf иногда вставляет пробел
# («§1 6a» — это §16a), затем буквенный суффикс, возможно тоже отбитый
# пробелом («§7 a» — это §7a). Буква «f» из суффикса исключена намеренно:
# после пробела она всегда значит «und folgende» («Vor §§ 74 ff»), а не
# суффикс параграфа.
#
# Часть комментария написана сразу к нескольким параграфам, и колонтитул
# тогда называет диапазон: «§§ 84–85», «§§ 28–37b». Нумерация Rz у такого
# блока сквозная, поэтому раздел у него один.
NUM = (r"(\d(?:\s?\d)*)\s?([a-eg-z])?"
       r"(?:\s*[–—-]\s*(\d(?:\s?\d)*)\s?([a-eg-z])?)?"
       r"(\s*f{1,2}\b)?")
VOR = re.compile(r"Vor\s*§+\s*" + NUM)
NACH = re.compile(r"Nach\s*§+\s*" + NUM)
PARA = re.compile(r"§+\s*" + NUM)
ART = re.compile(r"Art(?:ikel)?\s*([IVXL]+[a-z]?)(?![\w])")
# «Vor Art XIII bis XXVII» — вводный блок к серии статей EGZPO, у него своя
# нумерация Rz, и без отдельного адреса он сливается с Art XIII.
VOR_ART = re.compile(r"Vor\s*Art(?:ikel)?\s*([IVXL]+[a-z]?)"
                     r"(?:\s*(?:bis|–|—|-)\s*([IVXL]+[a-z]?))?(?![\w])")
# «§ 87 (§ 2 ZustG)», «Vor § 83a (§ 14 KSchG)» — часть комментария написана к
# чужой норме и вставлена внутрь параграфа. Нумерация Rz у такой вставки
# своя, поэтому скобка входит в опознание раздела, а не отбрасывается.
INSET = re.compile(r"^\s*\((§+[^)]{1,40})\)")
# «Verfahren § 87 (§ 25 ZustG)» — в скобке отсылка к другому закону, а не имя.
NOT_AUTHOR = re.compile(r"^[\(\[]|§|^\d")


def tidy(part):
    return re.sub(r"\s+", "", part or "")


def parse(line):
    s = " ".join(line.split())
    for rx, kind in ((VOR_ART, "vorart"), (VOR, "vor"), (NACH, "nach"),
                     (ART, "art"), (PARA, "para")):
        m = rx.search(s)
        if not m:
            continue
        if kind == "vorart":
            num, to, ff = m.group(1), m.group(2), False
            body = f"Art {num} bis {to}" if to else f"Art {num}"
        elif kind == "art":
            num, to, ff = m.group(1), None, False
            body = f"Art {num}"
        else:
            num = tidy(m.group(1)) + tidy(m.group(2))
            to = (tidy(m.group(3)) + tidy(m.group(4))) or None if m.group(3) else None
            ff = bool(m.group(5))
            if to:
                body = f"§§ {num}–{to}"
            elif ff:
                body = f"§§ {num} ff"
            else:
                body = f"§ {num}"
        display = {"vor": f"Vor {body}", "nach": f"Nach {body}",
                   "vorart": f"Vor {body}"}.get(kind, body)
        rest = s[m.end():]
        inset = INSET.match(rest)
        if inset:
            display = f"{display} ({inset.group(1)})"
            rest = rest[inset.end():]
        tail = rest.strip(" .,–-")
        author = None if (not tail or NOT_AUTHOR.match(tail)) else tail
        return {"kind": kind, "num": num, "to": to, "ff": ff,
                "inset": inset.group(1) if inset else None, "display": display}, author
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--pages", default="44-2216")
    a = ap.parse_args()

    from pypdf import PdfReader

    lo, hi = (int(x) for x in a.pages.split("-"))
    reader = PdfReader(a.pdf)
    pages, blank = {}, 0
    for pno in range(lo, hi + 1):
        text = reader.pages[pno - 1].extract_text() or ""
        first = next((l for l in text.splitlines() if l.strip()), "")
        section, author = parse(first)
        if section is None:
            blank += 1
            continue
        pages[str(pno)] = {**section, "section": section["display"],
                           "author": author, "raw": first.strip()[:80]}

    sections = sorted({v["section"] for v in pages.values()})
    named = sum(1 for v in pages.values() if v["author"])
    print(f"полос осмотрено: {hi - lo + 1}, колонтитул прочитан: {len(pages)}, без раздела: {blank}")
    print(f"разных номеров разделов: {len(sections)}, полос с именем автора: {named}")
    for pno in sorted(pages, key=int)[:3]:
        v = pages[pno]
        print(f"  f{pno}: раздел {v['section']!r}, автор {v['author']!r} | {v['raw']!r}")

    path = os.path.join(a.book, "work", "headers.json")
    json.dump({"pages": pages}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
