#!/usr/bin/env python3
"""Обмер полосы книги: что нужно знать, чтобы написать профиль.

    python scripts/probe_layout.py книга.pdf [--pages 12] [--yaml]

Читает несколько полос из середины книги и сообщает измеренные величины:
кегль тела и аппарата, положение колонтитула, подвала и колонцифры, сторону
и кегль номеров на полях. С ключом --yaml печатает черновик профиля с уже
подставленными долями.

Смысл в том, чтобы не подбирать доли вслепую. Три вещи, на которых
спотыкались все немецкие книги подряд:

* доли считаются ОТ ВЕРХА полосы, а не от края бумаги, и у файлов-Druckdatei
  начало координат смещено вверх: колонтитул стоит на отрицательном top, и
  положительная доля снимает вместе с ним четверть текста;
* `footnotes.bottom_band` — тоже доля ОТ ВЕРХА: строка ниже неё и мельче
  note_size_max считается сноской. Слишком большая доля оставляет аппарат в
  теле, и его номера читаются как номера Randnummer;
* `printed_page.band` — пара долей (сверху, снизу), причём нижняя отсчитывается
  как height * (1 - доля).
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

NUM = re.compile(r"\d{1,4}")
BARE_NUM = re.compile(r"^[\[\(]?(\d{1,4})[\]\)]?$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, default=12, help="сколько полос обмерить")
    ap.add_argument("--from", dest="frm", type=float, default=0.35,
                    help="с какой доли книги начинать (по умолчанию с трети: "
                         "впереди титул и оглавление)")
    ap.add_argument("--to", type=float, default=0.75)
    ap.add_argument("--yaml", action="store_true")
    a = ap.parse_args()

    pdf = pdfplumber.open(a.pdf)
    n = len(pdf.pages)
    idx = [int(n * (a.frm + (a.to - a.frm) * k / max(1, a.pages - 1))) for k in range(a.pages)]

    geom, sizes_len = set(), {}
    head_tops, body_tops, foot_bottoms, foot_texts = [], [], [], []
    note_tops, note_sizes, printed_hits = [], [], []
    margin_left, margin_right, margin_sizes = 0, 0, []
    for i in idx:
        pg = pdf.pages[i]
        h, w = float(pg.height), float(pg.width)
        geom.add((round(w, 1), round(h, 1)))
        lines = [l for l in P.chars_to_lines(pg.chars) if l["text"].strip()]
        pg.flush_cache()
        if len(lines) < 5:
            continue
        for l in lines:
            if l["size"]:
                sizes_len[round(l["size"], 2)] = sizes_len.get(round(l["size"], 2), 0) + len(l["text"])
        body_size = max(sizes_len, key=sizes_len.get)
        body = [l for l in lines if l["size"] and abs(l["size"] - body_size) < 0.4 and len(l["text"]) > 40]
        if not body:
            continue
        bl = statistics.median([l["x0"] for l in body])
        br = statistics.median([l["x1"] for l in body])
        # Колонтитул и подвал отделены от набора ОТБИВКОЙ, и только по ней их
        # и видно. Доли полосы для этого не годятся: на полосе, где длинных
        # строк мало (таблица, перечень), «выше тела» оказывается половина
        # текста, а у файлов-Druckdatei начало координат смещено вверх, и
        # верхняя доля вообще отрицательная.
        lines.sort(key=lambda l: l["top"])
        lead = statistics.median([lines[k + 1]["top"] - lines[k]["bottom"]
                                  for k in range(len(lines) - 1)])
        cut = max(4.0, lead + 4.0)
        k = 0
        while k + 1 < len(lines) and lines[k + 1]["top"] - lines[k]["bottom"] > cut:
            head_tops.append(lines[k]["top"])
            k += 1
        body_tops.append(lines[k]["top"])
        j = len(lines) - 1
        below = []
        while j > 0 and lines[j]["top"] - lines[j - 1]["bottom"] > cut:
            below.append(lines[j])
            j -= 1
        b_bot = lines[j]["bottom"]
        for l in below:
            foot_bottoms.append(l["bottom"])
            if len(l["text"]) <= 40:
                foot_texts.append(l["text"].strip())
                if BARE_NUM.match(l["text"].strip()):
                    printed_hits.append(("голая колонцифра", l["bottom"] / h))
        # Аппарат сносок берётся по НИЖНЕЙ ЧЕТВЕРТИ набора, а не по всему
        # низу полосы: у учебников мелким кеглем набран ещё и Kleindruck в
        # самом теле, и по «мельче тела» аппарат от него не отличить —
        # у Looschelders это 8.0 против 8.53, и ошибка увела бы Kleindruck
        # в сноски целиком.
        span = b_bot - lines[k]["top"] if b_bot > lines[k]["top"] else h
        tail = [l for l in lines if l["top"] > b_bot - 0.25 * span
                and l["size"] and l["size"] < body_size - 0.6 and len(l["text"]) > 25]
        if tail:
            note_tops.append(min(l["top"] for l in tail) / h)
            note_sizes.append(statistics.median([l["size"] for l in tail]))
        # номера на полях
        for l in lines:
            for wd in l["words"]:
                if not NUM.fullmatch(wd["text"]):
                    continue
                if wd["x1"] < bl - 2:
                    margin_left += 1
                    margin_sizes.append(round(wd["size"], 2))
                elif wd["x0"] > br + 2:
                    margin_right += 1
                    margin_sizes.append(round(wd["size"], 2))
    pdf.close()

    body_size = max(sizes_len, key=sizes_len.get) if sizes_len else None
    (w, h) = sorted(geom)[0] if geom else (0, 0)
    print(f"полос в файле: {n}, обмерено: {len(idx)}")
    print(f"полоса: {w}×{h}" + ("" if len(geom) == 1 else f"  (РАЗНЫЕ: {sorted(geom)[:4]})"))
    print(f"кегль тела: {body_size}")
    top5 = sorted(sizes_len.items(), key=lambda kv: -kv[1])[:5]
    print(f"кегли по объёму текста: {top5}")
    if head_tops:
        print(f"колонтитул: top {min(head_tops):.1f}..{max(head_tops):.1f} "
              f"(доли {min(head_tops)/h:.3f}..{max(head_tops)/h:.3f})")
    if body_tops:
        print(f"тело начинается: top {min(body_tops):.1f} (доля {min(body_tops)/h:.3f})")
    if foot_bottoms:
        print(f"подвал: bottom {min(foot_bottoms):.1f}..{max(foot_bottoms):.1f} "
              f"(доли снизу {1-max(foot_bottoms)/h:.3f}..{1-min(foot_bottoms)/h:.3f})")
        print(f"строки подвала: {foot_texts[:6]}")
    if note_tops:
        note_tops.sort()
        print(f"аппарат сносок: кегль {statistics.median(note_sizes):.2f}, "
              f"начинается с долей {note_tops[0]:.3f}..{note_tops[-1]:.3f}")
    else:
        print("аппарат сносок: не найден (мелких строк внизу нет)")
    print(f"номера на полях: слева {margin_left}, справа {margin_right}"
          + (f", кегли {sorted(set(margin_sizes))}" if margin_sizes else ""))
    if printed_hits:
        print(f"колонцифра отдельной строкой: {len(printed_hits)} раз, доля снизу "
              f"{1-max(x[1] for x in printed_hits):.3f}")

    if a.yaml:
        head_band = (max(head_tops) + min(body_tops)) / 2 / h if head_tops and body_tops else 0.06
        note_band = (min(note_tops) - 0.03) if note_tops else 0.70
        pp_band = 1 - (min(foot_bottoms) - 2) / h if foot_bottoms else 0.10
        print("\n--- черновик профиля ---")
        print(f"""units:
  - type: "Rn."
    id_prefix: "rn"
    mode: margin

margin:
  scope: page
  pad: 0.0

footnotes:
  mode: font_bottom
  bottom_band: {note_band:.2f}
  note_size_max: {(statistics.median(note_sizes) + 0.2) if note_sizes else 0.0:.1f}

printed_page:
  band: [0.0, {pp_band:.2f}]
  max_chars: 40

junk:
  header_band: {head_band:.3f}""")


if __name__ == "__main__":
    main()
