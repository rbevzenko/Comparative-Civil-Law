#!/usr/bin/env python3
"""Возвращает в текст слова, которые в PDF нарисованы контурами.

    python scripts/fill_outline_gaps.py --pdf файл.pdf --out work/patches.json \
        [--pages 1-200] [--scale 3.0] [--conf 70] [--workers 4] [--lang deu]

ЗАЧЕМ. В распечатках beck-online выделенное полужирным не вшито в текстовый
слой: оно нарисовано векторными контурами. Ни pdfplumber, ни pdftotext его
не видят. На полосе § 227 МюКо предложение выходит таким:

    «…kann ein notwehrfähiger Angriff ausgehen, nicht hingegen von Tieren»

а напечатано: «kann ein notwehrfähiger Angriff **nur von Menschen**
ausgehen». Потеряно ровно то, что автор выделил, то есть ключевое слово.
Заодно контурами нарисованы Randnummern на правом поле и часть заголовков —
без них не собрать ни адрес карточки, ни иерархию.

КАК. Полоса рисуется в картинку и распознаётся целиком ОДИН раз, после чего
слова распознавания сверяются со словами текстового слоя по координатам.
Слово, которому в текстовом слое ничего не соответствует, и есть потерянное.
Обратный порядок (искать дыры в координатах и распознавать их по кусочкам)
пробовали: он не видит потерь в начале и в конце строки, а на выключке
принимает за дыру растянутый межсловный пробел.

Распознанному верим не всякому: ниже порога уверенности слово отбрасывается,
а стрелка перекрёстной ссылки «→», которую tesseract отдаёт как «(>» или
«+», приводится к своему знаку. Верхняя и нижняя полосы не трогаются вовсе:
там колонтитул и адрес печати, которые всё равно снимаются как мусор.
"""

import argparse
import json
import multiprocessing
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P

try:
    import pdfplumber
    import pypdfium2 as pdfium
    import pytesseract
except ImportError as exc:
    sys.exit(f"Нужны pdfplumber, pypdfium2 и pytesseract: {exc}")

ARROW = {"(>": "(→", ">": "→", "+": "→", "—": "→", "-": "→", "»": "→"}


_DOC = {}


def _open(path):
    """Открыть файл ОДИН раз на процесс.

    Открывать его на каждую полосу нельзя: у распечаток МюКо файл весит до
    ста мегабайт, и повторный разбор его оглавления стоит дороже самого
    распознавания. На файле в 1222 полосы разница — часы.
    """
    if not _DOC:
        _DOC["pdfium"] = pdfium.PdfDocument(path)
        _DOC["plumber"] = pdfplumber.open(path)
    return _DOC["pdfium"], _DOC["plumber"]


def page_patches(args):
    """Потерянные слова одной полосы. Отдельная функция — её зовут процессы."""
    path, i, scale, conf_min, lang, band = args
    pdf, pl = _open(path)
    img = pdf[i].render(scale=scale).to_pil()
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    page = pl.pages[i]
    height = float(page.height)
    lines = P.chars_to_lines(page.chars)
    page.flush_cache()
    page.get_textmap.cache_clear()

    have = []
    for ln in lines:
        for w in ln.get("words", []):
            have.append((w["x0"], w["x1"], ln["top"] - 2, ln["bottom"] + 2))

    out = []
    for k, raw in enumerate(data["text"]):
        txt = raw.strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][k])
        except (TypeError, ValueError):
            continue
        x0 = data["left"][k] / scale
        x1 = (data["left"][k] + data["width"][k]) / scale
        y0 = data["top"][k] / scale
        y1 = (data["top"][k] + data["height"][k]) / scale
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if cy < height * band or cy > height * (1 - band):
            continue                      # колонтитул и адрес печати — мусор
        if any(a <= cx <= b and t <= cy <= bo for a, b, t, bo in have):
            continue
        if txt in ARROW:
            txt, conf = ARROW[txt], max(conf, conf_min)
        elif conf < conf_min:
            continue
        out.append({"x0": round(x0, 1), "x1": round(x1, 1), "top": round(y0, 1),
                    "bottom": round(y1, 1), "text": txt, "conf": round(conf)})
    return i + 1, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages")
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--conf", type=float, default=70.0)
    ap.add_argument("--band", type=float, default=0.035,
                    help="доля высоты сверху и снизу, которая не трогается")
    ap.add_argument("--lang", default="deu")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()

    with pdfplumber.open(a.pdf) as pl:
        total = len(pl.pages)
    idx = P.parse_range(a.pages, total)

    done = {}
    if os.path.exists(a.out):
        done = json.load(open(a.out, encoding="utf-8"))
    todo = [i for i in idx if str(i + 1) not in done]
    print(f"полос: {total}, к распознаванию: {len(todo)}, уже есть: {len(done)}", flush=True)

    jobs = [(a.pdf, i, a.scale, a.conf, a.lang, a.band) for i in todo]
    n = 0
    # Метод spawn, а не fork: скрипт запускают из многопоточной среды, и
    # форк такого процесса даёт пул, который встаёт намертво — рабочие
    # ждут задания, родитель ждёт результата, и никто не двигается.
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=ctx) as pool:
        for pno, patches in pool.map(page_patches, jobs, chunksize=4):
            done[str(pno)] = patches
            n += 1
            if n % 25 == 0:
                json.dump(done, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  распознано полос: {n}/{len(todo)}", flush=True)
    json.dump(done, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    words = sum(len(v) for v in done.values())
    print(f"Готово. Возвращено слов: {words} на {len(done)} полосах → {a.out}")


if __name__ == "__main__":
    main()
