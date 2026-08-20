#!/usr/bin/env python3
"""Акт, параграф и автор в адресе карточки.

    python qualify_sections.py --book <каталог> --pdf <файл> [--dry-run]

Запускать после extract.py, ДО отчёта о качестве и выгрузки. Требует
work/headers.json — его готовит read_headers.py.

Чинит четыре вещи; каждая по отдельности ломает ссылку.

**Код акта входит в адрес.** Том комментирует четыре акта — EGJN, JN, EGZPO и
ZPO, — и номера у них пересекаются сплошь: «§ 1» есть и в JN, и в ZPO, «Art I»
и в EGJN, и в EGZPO. Без кода акта карточки сталкиваются по `external_id`, а
загрузка идемпотентна по нему: одна молча затирает другую. Границы актов
берутся из узлов верхнего уровня зашитого оглавления, оформление адреса — по
конвенции самой книги с оборота титула: у ZPO код не пишется, у остальных
пишется после номера («§ 7 JN Rz 5», «Art IX EGJN Rz 17»).

**Раздел берётся из колонтитула.** В оглавлении файла 86 узлов на 2173 полосы
тела, и это Teile и Titel, а не параграфы. Колонтитул называет параграф на
каждой полосе.

**Граница параграфа проходит по строке, а не по полосе.** Комментарий к § 51
кончается в середине той полосы, где заголовком «§ 52. (1) …» начинается
следующий. Параграфы не выдумываются: их список берётся из колонтитулов, а
тело используется только чтобы найти, ГДЕ на полосе стоит заголовок.

**Автор параграфа входит в ссылку.** Издательство предписывает это на обороте
титула: «Gitschthaler in Rechberger/Klicka, ZPO5 §132 Rz1». Имя стоит в
колонтитуле verso; ключ карты — пара (акт, раздел), одного номера мало.

И последнее: аппарат параграфа — текст закона, «Lit:», «[Fassung …]» — стоит
между последним Rz предыдущего параграфа и первым Rz следующего. Своего
номера у него нет, и пайплайн приписывает его к последней карточке
ПРЕДЫДУЩЕГО параграфа. Здесь карточка режется по заголовку следующего
раздела, а снятый хвост уходит к его первой карточке — под тот адрес, где его
и станут искать.
"""

import argparse
import json
import os
import re
import sys

ACTS = [
    ("EGJN", re.compile(r"Einführungsgesetz zur Jurisdiktionsnorm")),
    ("JN", re.compile(r"^Jurisdiktionsnorm")),
    ("EGZPO", re.compile(r"Einführungsgesetz zur Zivilprozessordnung")),
    ("ZPO", re.compile(r"^Zivilprozessordnung")),
]
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def render_address(act, head, rz):
    # ZPO — основной акт тома, его код в ссылке не пишется; так же оформлены
    # примеры на обороте титула.
    if act != "ZPO":
        head = f"{head} {act}"
    return f"{head} Rz {rz}"


def key_of(act, head):
    return act + re.sub(r"[^\w]", "", head)


def heading_rx(sec):
    """Заголовок раздела в начале строки тела."""
    num = re.escape(sec["num"])
    if sec.get("inset"):
        # У вставки нет своего заголовка в теле: она начинается текстом чужой
        # нормы. Такой раздел переключается по полосе.
        return re.compile(r"(?!x)x")
    if sec["kind"] == "vorart":
        return re.compile(rf"^Vor\s*Art(?:ikel)?\s*{num}\b")
    if sec["kind"] == "vor":
        return re.compile(rf"^Vor\s*§+\s*{num}\b")
    if sec["kind"] == "nach":
        return re.compile(rf"^Nach\s*§+\s*{num}\b")
    if sec["kind"] == "art":
        return re.compile(rf"^Art(?:ikel)?\s*{num}\.\s")
    return re.compile(rf"^§\s*{num}\.\s")


# Заголовок раздела в теле полосы. Нужен потому, что колонтитул называет не
# все разделы. Две причины, и обе дают столкновения id.
#
# Первая: на f66 подряд кончаются Art X, Art XI и Art XII, а колонтитул этой
# полосы говорит только «Art XIII» — Rz трёх пропущенных статей достаются
# предыдущему разделу.
#
# Вторая: вводные блоки. На f214 в теле стоит заголовок «Vor §34» и под ним
# своя нумерация с Rz 1, а колонтитул всей полосы — «§§ 34–35». Без разбора
# тела этот Rz 1 сталкивается с Rz 1 предыдущего параграфа.
BODY_ART = re.compile(r"^Art(?:ikel)?\s+([IVXL]+)\.\s")
# Заголовок вводного блока стоит ОТДЕЛЬНОЙ строкой и состоит только из
# «Vor §34» (иногда с перечислением: «Vor §§83a, 83b»). Якорь на конец строки
# здесь обязателен: без него правило ловит перенос перекрёстной ссылки
# («Vor §76 Rz3) und …»), и книга получает разделы из чужих отсылок.
BODY_VOR = re.compile(r"^Vor\s*§+\s*(\d+(?:[a-eg-z])?)"
                      r"(?:\s*(?:,|und|u)\s*§*\s*\d+[a-z]?)*\s*$")
BODY_NACH = re.compile(r"^Nach\s*§+\s*(\d+(?:[a-eg-z])?)"
                       r"(?:\s*(?:,|und|u)\s*§*\s*\d+[a-z]?)*\s*$")
BODY_PARA = re.compile(r"^§\s*(\d+(?:[a-eg-z])?)\.\s")


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(text):
    total, prev = 0, 0
    for ch in reversed(text.upper()):
        val = ROMAN.get(ch, 0)
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total


def order_key(sec):
    """Порядковый ключ раздела внутри акта.

    Комментарий идёт по возрастанию номеров, и это единственный надёжный
    признак, отличающий настоящий заголовок раздела от текста ЧУЖОЙ нормы,
    процитированного внутри параграфа: на f1370 внутри комментария к § 271
    стоит «§ 3. …» — это § 3 IPRG, а не третий параграф ZPO, и без проверки
    на возрастание книга откатывается на двести с лишним параграфов назад.

    «Vor § N» идёт перед самим N, «Nach § N» — после него.
    """
    num = sec.get("num") or ""
    if sec["kind"] in ("art", "vorart"):
        base = roman_to_int(re.match(r"[IVXLC]*", num.upper()).group(0) or "I")
        suffix = num[len(re.match(r"[IVXLC]*", num.upper()).group(0)):]
    else:
        m = re.match(r"(\d+)([a-z]*)", num)
        base, suffix = (int(m.group(1)), m.group(2)) if m else (0, "")
    stage = {"vor": 0, "vorart": 0, "para": 1, "art": 1, "nach": 2}[sec["kind"]]
    return (base, suffix, stage, sec.get("inset") or "")


def covered(section, num):
    """Номер лежит СТРОГО внутри диапазона, объявленного колонтитулом."""
    def val(x):
        m = re.match(r"(\d+)", x or "")
        return int(m.group(1)) if m else None

    lo, hi, n = val(section.get("num")), val(section.get("to")), val(num)
    return None not in (lo, hi, n) and lo < n <= hi


def act_ranges(pdf_path, body_end):
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    tops = []

    def walk(node, depth=0):
        for item in node:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            if depth:
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                continue
            tops.append((page, CONTROL.sub("", str(getattr(item, "title", ""))).strip()))

    walk(reader.outline or [])
    tops.sort()
    out = []
    for i, (page, title) in enumerate(tops):
        code = next((c for c, rx in ACTS if rx.search(title)), None)
        if code is None:
            continue
        end = next((p - 1 for p, _ in tops[i + 1:] if p > page), body_end)
        out.append((page, min(end, body_end), code))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--body-end", type=int, default=2216)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    hpath = os.path.join(a.book, "work", "headers.json")
    if not os.path.exists(hpath):
        sys.exit("нет work/headers.json — сначала read_headers.py")
    head = json.load(open(hpath, encoding="utf-8"))["pages"]
    by_page = {int(k): v for k, v in head.items()}

    ranges = act_ranges(a.pdf, a.body_end)
    if not ranges:
        sys.exit("в оглавлении файла не нашлось узлов с кодами актов")
    print("диапазоны актов из оглавления:")
    for lo, hi, code in ranges:
        print(f"  {code:6s} f{lo}–{hi}")

    def act_of(page):
        return next((c for lo, hi, c in ranges if lo <= page <= hi), None)

    pages = {}
    for line in open(os.path.join(a.book, "work", "pages.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        pages[p["pdf_page"]] = p
    order = sorted(pages)

    # Полосы без колонтитула — это шмуцтитулы актов и первые полосы разделов;
    # раздел у них тот же, что у следующей полосы с колонтитулом.
    filled = 0
    for i, pno in enumerate(order):
        if pno in by_page:
            continue
        nxt = next((by_page[q] for q in order[i + 1:] if q in by_page), None)
        if nxt:
            by_page[pno] = nxt
            filled += 1

    # Автор: ключ — пара (акт, раздел). Одного номера мало: «§ 1» есть и в JN
    # (Mayr), и в ZPO (Fucik).
    votes = {}
    for pno, v in by_page.items():
        act = act_of(pno)
        if act and v.get("author"):
            votes.setdefault((act, v["section"]), {}).setdefault(v["author"], 0)
            votes[(act, v["section"])][v["author"]] += 1
    authors = {k: max(v, key=v.get) for k, v in votes.items()}

    def author_at(pno, act, sec):
        """Автор для карточки: сначала по её собственной полосе.

        Имя стоит в колонтитуле verso, и стоит оно там не при разделе, а при
        материале полосы. Поэтому для разделов, которых колонтитул по имени
        не называет (Art X, XI и XII кончаются на одной полосе с Art XIII),
        карта (акт, раздел) пуста, а полоса автора всё равно знает.
        """
        for q in (pno, pno + 1, pno - 1, pno + 2, pno - 2):
            v = by_page.get(q)
            if v and v.get("author"):
                return v["author"]
        return authors.get((act, sec))
    print(f"\nполос: {len(order)}, раздел из колонтитула: {len(by_page) - filled}, "
          f"унаследован первой полосой раздела: {filled}")
    print(f"пар (акт, раздел) с именем автора: {len(authors)}, "
          f"из них с разночтением: {sum(1 for v in votes.values() if len(v) > 1)}")

    # Точки переключения собираются из двух источников. Колонтитул называет
    # раздел на каждой полосе, но не всякий раздел успевает в него попасть:
    # если на полосе кончаются три статьи подряд, колонтитул назовёт одну.
    # Поэтому вторым источником берутся заголовки в самом теле — они же дают
    # и точное место переключения внутри полосы.
    # Точки переключения собираются из двух источников и проверяются одним
    # правилом. Колонтитул называет раздел на каждой полосе, но не всякий
    # раздел успевает в него попасть (на f66 подряд кончаются Art X, XI и XII,
    # а колонтитул называет только Art XIII; на f214 в теле стоит «Vor §34»,
    # а колонтитул всей полосы — «§§ 34–35»). Тело же называет и то, чего
    # разделом не является: процитированную чужую норму. Отсеивает их
    # возрастание: комментарий идёт по номерам вперёд и назад не возвращается.
    # Интервал, в котором вообще может лежать заголовок, найденный в теле:
    # его задают колонтитулы соседних полос. Одной проверки на возрастание
    # мало — процитированный «§ 164. (1) …» внутри обзора к Vor §§ 155 ff
    # тоже идёт вперёд, и, приняв его, книга отбрасывает назад всё, что после.
    found, from_header, by_page_only, rejected = [], [], [], []
    cur_sec, cur_key, cur_act = None, None, None
    switches = []
    for pno in order:
        act = act_of(pno)
        if act is None:
            continue
        if act != cur_act:
            cur_act, cur_key, cur_sec = act, None, None
        H = pages[pno]["height"] or 1
        cands = []
        v = by_page.get(pno)
        if v is not None and (act, v["display"]) != cur_sec:
            sec = {k: v.get(k) for k in ("kind", "num", "to", "ff", "inset", "display")}
            rx = heading_rx(sec)
            top = next((ln["top"] / H for ln in pages[pno]["lines"]
                        if rx.match(ln["text"].strip())), None)
            cands.append((top if top is not None else 0.0, sec, top is not None, "колонтитул"))
        rules = ([(BODY_ART, "art")] if act in ("EGJN", "EGZPO")
                 else [(BODY_VOR, "vor"), (BODY_NACH, "nach"), (BODY_PARA, "para")])
        hdr = by_page.get(pno)
        for ln in pages[pno]["lines"]:
            text = ln["text"].strip()
            m = kind = None
            for rx, k in rules:
                m = rx.match(text)
                if m:
                    kind = k
                    break
            if not m:
                continue
            num = m.group(1)
            if hdr and hdr.get("to") and kind == "para" and covered(hdr, num):
                continue
            if hdr and hdr.get("inset") and kind == "para":
                continue
            display = {"art": f"Art {num}", "vor": f"Vor § {num}",
                       "nach": f"Nach § {num}", "para": f"§ {num}"}[kind]
            cands.append((ln["top"] / H, {"kind": kind, "num": num, "to": None,
                                          "ff": False, "inset": None,
                                          "display": display}, True, "тело"))
        for top, sec, precise, src in sorted(cands, key=lambda c: c[0]):
            if (act, sec["display"]) == cur_sec:
                continue
            key = order_key(sec)
            if cur_key is not None and key <= cur_key:
                rejected.append((pno, sec["display"], src))
                continue
            switches.append((pno, top, act, sec))
            (found if src == "тело" else from_header).append(sec)
            if not precise:
                by_page_only.append((pno, sec["display"]))
            cur_sec, cur_key = (act, sec["display"]), key

    print(f"разделов: {len(switches)} (из тела {len(found)}, из колонтитула "
          f"{len(from_header)}), переключены по полосе: {len(by_page_only)}")
    print(f"отклонено как возврат назад (чужая норма в цитате): {len(rejected)}")
    for pno, disp, src in rejected[:6]:
        print(f"  f{pno}: {disp} ({src})")

    path = os.path.join(a.book, "output", "cards.jsonl")
    cards = [json.loads(l) for l in open(path, encoding="utf-8")]

    def start_of(card):
        page = card.get("page_start")
        box = next((b for b in (card.get("bbox") or []) if b["pdf_page"] == page), None)
        return (page, box["bbox"][1] if box else 0.0)

    pos_of = {id(c): start_of(c) for c in cards}
    seen, counts, skipped, no_author = {}, {}, 0, 0
    for c in cards:
        pos = pos_of[id(c)]
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
        _, _, act, secd = hit
        sec = secd["display"]
        rz = c["unit_number"]
        author = authors.get((act, sec)) or author_at(pos[0], act, sec)
        if not author:
            no_author += 1
        c["law"] = act
        c["section"] = f"{act} {sec}"
        c["author"] = author
        c["address"] = render_address(act, sec, rz)
        c["citation"] = (f"{author} in Rechberger/Klicka, ZPO⁵ {c['address']}" if author
                         else f"Rechberger/Klicka, ZPO⁵ {c['address']}")
        c["external_id"] = f"{c['book_id']}:{c['unit_type'].lower()}:{key_of(act, sec)}/{rz}"
        c["id"] = f"{c['book_id']}-{c['unit_type'].lower()}{key_of(act, sec)}-{rz}"
        nodes = [CONTROL.sub("", h).strip() for h in (c.get("hierarchy") or [])]
        c["hierarchy"] = [re.sub(r"\s{2,}", " ", n) for n in nodes if n] + [sec]
        counts[act] = counts.get(act, 0) + 1
        seen.setdefault(c["external_id"], []).append(c)

    # Хвост карточки за границей раздела — аппарат следующего параграфа.
    ordered = sorted((c for c in cards if pos_of[id(c)][0] is not None),
                     key=lambda c: pos_of[id(c)])
    trimmed, trim_chars, untrimmed = 0, 0, []
    for i, c in enumerate(ordered):
        pos = pos_of[id(c)]
        nxt = next((s for s in switches if (s[0], s[1]) > (pos[0], pos[1] + 1e-9)), None)
        if nxt is None:
            continue
        after = pos_of[id(ordered[i + 1])] if i + 1 < len(ordered) else (10 ** 6, 0.0)
        if after <= (nxt[0], nxt[1]):
            continue
        m = re.compile(heading_rx(nxt[3]).pattern, re.M).search(c["text"])
        if not m or m.start() < 20:
            untrimmed.append((c["external_id"], nxt[3]["display"]))
            continue
        tail = c["text"][m.start():].strip()
        trim_chars += len(c["text"]) - m.start()
        c["text"] = c["text"][:m.start()].rstrip()
        c["page_end"] = nxt[0] if nxt[1] > 0.125 else nxt[0] - 1
        pp = pages.get(c["page_end"], {}).get("printed_page")
        if pp:
            c["printed_page_end"] = pp
        heir = ordered[i + 1]
        heir["text"] = tail + "\n" + heir["text"]
        if heir.get("page_start") is None or nxt[0] < heir["page_start"]:
            heir["page_start"] = nxt[0]
            pp = pages.get(nxt[0], {}).get("printed_page")
            if pp:
                heir["printed_page_start"] = pp
        trimmed += 1
    print(f"аппарат раздела переехал в свой раздел: {trimmed} границ, знаков: {trim_chars}")
    if untrimmed:
        print(f"  заголовок для обрезки не нашёлся: {len(untrimmed)}")
        for eid, sec in untrimmed[:6]:
            print(f"    {eid} → {sec}")

    # Пять мест в книге дают одинаковый адрес дважды: комментарий к разделу
    # разбит на два блока, и нумерация Rz во втором начинается заново, а
    # заголовка, по которому можно было бы отделить второй блок, в тексте
    # нет — ни в колонтитуле, ни в теле. Адрес у таких карточек остаётся тот,
    # что печатает книга, а вот `external_id` разводится типографской
    # страницей: загрузка идемпотентна по нему, и без этого одна карточка
    # молча затёрла бы другую.
    split_ids = []
    for eid, group in list(seen.items()):
        if len(group) < 2:
            continue
        for c in sorted(group, key=lambda x: pos_of[id(x)])[1:]:
            page = c.get("printed_page_start") or c.get("page_start")
            c["external_id"] = f"{eid}@{page}"
            c["id"] = f"{c['id']}-{page}"
            c["address_ambiguous"] = True
            split_ids.append((eid, page))
        seen[eid] = group[:1]
    if split_ids:
        print(f"\nадрес встретился дважды, id разведён страницей: {len(split_ids)}")
        for eid, page in split_ids:
            print(f"  {eid} → {eid}@{page}")

    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print(f"\nкарточек с адресом: {sum(counts.values())}, без раздела: {skipped}, "
          f"без автора: {no_author}")
    for code in sorted(counts):
        print(f"  {code:6s} {counts[code]}")
    if dupes:
        print(f"ОСТАЛИСЬ СТОЛКНОВЕНИЯ id: {len(dupes)}")
        for k, v in list(dupes.items())[:8]:
            print(f"  {k}: полосы файла {[x.get('page_start') for x in v]}")
    else:
        print("столкновений id нет")

    if a.dry_run:
        for c in cards[:2] + cards[-2:]:
            print(f"  {c.get('external_id'):36s} | {c.get('citation')}")
        print("dry-run: файл не тронут")
        return

    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: qa_report.py")


if __name__ == "__main__":
    main()
