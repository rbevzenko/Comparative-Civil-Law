#!/usr/bin/env python3
"""Двухколонная полоса → модель страницы с правильным порядком чтения.

    python scripts/pages_two_column.py книга.pdf --book books/<id> --profile … \
        --split 277 [--gutter 8] [--pages 24-260] [--skip-done]

Обёртка вокруг `pages_digital.py` для книг, набранных в две колонки, где
обе колонки — ОДИН И ТОТ ЖЕ текст, читаемый слева направо. (Для книг, где
колонки — два разных языка, есть `pages_column.py`: там каждая колонка
уходит в свою книгу.)

Обычная сборка строк идёт через всю полосу и склеивает строку левой колонки
со строкой правой:

    «negligence and also for breach of implied  Self-assessment questions»

— то есть непригодно ни для чтения, ни для эмбеддинга.

Строки собираются как обычно, а потом каждая проверяется на границу колонок:

* строка, у которой в зазоре `[split - gutter, split + gutter]` нет ни
  одного знака, — это ДВЕ строки, левая и правая; она делится;
* строка, знаки которой идут через зазор сплошь, — это заголовок во всю
  полосу; она остаётся целой. Просвета не бывает и у обычной строки, если
  левая колонка дотянулась до самой границы, поэтому есть ещё порог
  `--wide-size`: во всю полосу набраны только заголовки глав, а тело обеих
  колонок — кегль 9–11.

Дальше полоса режется этими сплошными строками на блоки, и внутри каждого
блока сначала идёт левая колонка сверху вниз, потом правая. Так получается
настоящий порядок чтения: заголовок, левая колонка под ним, правая колонка
под ним, следующий заголовок.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.claude/skills/synced/complaw-corpus/scripts")
sys.path.insert(0, SKILL)
import pipelib as P
import pages_digital as PD

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")


# Настоящая сборка строк запоминается ДО подмены: columnar() зовёт её сам,
# и без этого получилась бы бесконечная рекурсия.
BUILD_LINES = P.chars_to_lines


def two_column_lines(chars, split, gutter, wide_size=None):
    rows = P.cluster_lines(chars)
    blocks, cur = [], {"left": [], "right": []}
    out = []

    def flush():
        if cur["left"] or cur["right"]:
            out.extend(cur["left"])
            out.extend(cur["right"])
            cur["left"], cur["right"] = [], []

    for row in rows:
        row = sorted(row, key=lambda c: c["x0"])
        # Знак, начавшийся левее границы и кончившийся правее, считается
        # левым — иначе широкая литера заголовка («A» кеглем 44) сама
        # создаёт мнимый просвет шириной в собственную ширину.
        left_edge = max((c["x1"] for c in row if c["x0"] < split), default=None)
        right_edge = min((c["x0"] for c in row if c["x0"] >= split), default=None)
        # Строка во всю полосу — та, у которой на границе колонок нет
        # просвета: знаки идут через неё подряд. Проверять «знак пересекает
        # split» нельзя: знак шириной в пять пунктов, стоящий у самого края
        # левой колонки, формально попадает в допуск и превращает обычную
        # двухколонную строку в мнимый заголовок.
        spans = (left_edge is not None and right_edge is not None
                 and right_edge - left_edge < gutter)
        # Просвета нет и у обычной двухколонной строки, если левая колонка
        # дотянулась до самой границы. Отличает кегль: во всю полосу набраны
        # только заголовки глав, тело обеих колонок — кегль 9–11.
        if spans and wide_size is not None:
            spans = max((c.get("size") or 0) for c in row) >= wide_size
        if spans:
            flush()
            line = BUILD_LINES(row)
            out.extend(line)
            continue
        left = [c for c in row if c["x0"] < split]
        right = [c for c in row if c["x0"] >= split]
        if left:
            cur["left"].extend(BUILD_LINES(left))
        if right:
            cur["right"].extend(BUILD_LINES(right))
    flush()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--book", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--split", type=float, required=True, help="граница колонок по x")
    ap.add_argument("--gutter", type=float, default=8.0,
                    help="ширина зазора, в котором у двух колонок знаков не бывает")
    ap.add_argument("--wide-size", type=float, default=None,
                    help="минимальный кегль строки во всю полосу; ниже него строка "
                         "без просвета всё равно считается двухколонной")
    ap.add_argument("--pages")
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()

    prof = P.load_profile(a.profile)
    junk_rx = P.compile_patterns(prof.get("junk", {}).get("patterns"))
    d = P.book_dirs(a.book)
    cache = os.path.join(d["cache"], "pages")
    os.makedirs(cache, exist_ok=True)

    # build_page зовёт P.chars_to_lines; подменяем её на колоночную сборку.
    original = P.chars_to_lines

    def columnar(chars):
        return two_column_lines(chars, a.split, a.gutter, a.wide_size)

    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        done = 0
        P.chars_to_lines = columnar
        PD.P.chars_to_lines = columnar
        try:
            for i in idx:
                path = os.path.join(cache, f"page-{i + 1:05d}.json")
                if a.skip_done and os.path.exists(path):
                    done += 1
                    continue
                built = PD.build_page(pdf.pages[i], i, prof, junk_rx)
                P.write_json(path, built)
                done += 1
                if done % 50 == 0:
                    print(f"  полос разобрано: {done}/{len(idx)}", flush=True)
        finally:
            P.chars_to_lines = original
            PD.P.chars_to_lines = original

    wanted = sorted({i + 1 for i in idx} | (
        {int(n[5:10]) for n in os.listdir(cache) if n.startswith("page-") and n.endswith(".json")}
        if a.skip_done else set()))
    pages = []
    for pno in wanted:
        path = os.path.join(cache, f"page-{pno:05d}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                pages.append(json.load(fh))

    P.write_jsonl(os.path.join(d["work"], "pages.jsonl"), pages)
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf),
        "source_sha256": P.sha256_file(a.pdf),
        "branch": "A",
        "method": "digital",
        "profile": prof.get("id"),
        "columns": 2,
        "split": a.split,
        "pages_requested": len(idx),
        "pages_built": len(pages),
        "pages_empty": sum(1 for p in pages if p.get("empty")),
        "schema_version": P.SCHEMA_VERSION,
    })
    print(f"Страниц в модели: {len(pages)}, пустых: {sum(1 for p in pages if p.get('empty'))}")
    print(f"Записано: {d['work']}/pages.jsonl")
    print("Дальше: extract.py")


if __name__ == "__main__":
    main()
