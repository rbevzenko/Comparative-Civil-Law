#!/usr/bin/env python3
"""Разворот, отсканированный одним листом → две полосы книги.

    python scripts/pages_spread.py книга.pdf --book books/<id> --profile … \
        --split 421 [--pages 16-128]

Обёртка вокруг `pages_digital.py` для сканов, где на одном листе файла
сняты ДВЕ страницы книги. Сборка строк идёт через весь лист и склеивает
строку левой страницы со строкой правой:

    «which the court or the legislator holds appropriate? Is the defendant to be distin»

Здесь лист делится по `--split` на две полосы, и каждая разбирается
отдельно: своя колонцифра, свой колонтитул, свой аппарат сносок. В модели
страницы у обеих остаётся НОМЕР ЛИСТА (`pdf_page`), а различает их
типографская колонцифра (`printed_page`) — она и есть адрес.

Отличие от `pages_two_column.py`: там две колонки одной страницы, и порядок
чтения внутри полосы; здесь две разные страницы книги, и у каждой свой
адрес.

Отличие от `pages_column.py`: там колонки — два разных языка, и каждая
уходит в свою книгу.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json

SKILL = os.path.expanduser("~/.claude/skills/synced/complaw-corpus/scripts")
sys.path.insert(0, SKILL)
import pipelib as P
import pages_digital as PD

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")


class Half:
    """Половина листа: то, что нужно build_page."""

    def __init__(self, page, lo, hi):
        self.height = float(page.height)
        self.width = hi - lo if hi < 10 ** 5 else float(page.width) - lo
        self.chars = [dict(c) for c in page.chars if lo <= c["x0"] < hi]
        # build_page считает координаты от левого края полосы, а не листа.
        for c in self.chars:
            c["x0"] -= lo
            c["x1"] -= lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--book", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--split", type=float, required=True, help="граница страниц по x")
    ap.add_argument("--pages")
    a = ap.parse_args()

    prof = P.load_profile(a.profile)
    junk_rx = P.compile_patterns(prof.get("junk", {}).get("patterns"))
    d = P.book_dirs(a.book)

    pages = []
    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        for n, i in enumerate(idx, 1):
            src = pdf.pages[i]
            for lo, hi in ((0.0, a.split), (a.split, 10 ** 6)):
                half = Half(src, lo, hi)
                # Пустая половина всё равно попадает в модель: она держит
                # МЕСТО страницы. Без неё сбивается счёт при достройке
                # колонцифры по порядку (--sequential), а карточки из неё
                # всё равно не выйдет — строк нет.
                built = PD.build_page(half, i, prof, junk_rx)
                pages.append(built)
            if n % 50 == 0:
                print(f"  листов разобрано: {n}/{len(idx)}", flush=True)

    P.write_jsonl(os.path.join(d["work"], "pages.jsonl"), pages)
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf),
        "source_sha256": P.sha256_file(a.pdf),
        "branch": "A",
        "method": "digital",
        "profile": prof.get("id"),
        "spread": True,
        "split": a.split,
        "pages_requested": len(idx),
        "pages_built": len(pages),
        "pages_empty": sum(1 for p in pages if p.get("empty")),
        "schema_version": P.SCHEMA_VERSION,
    })
    print(f"Полос в модели: {len(pages)} из {len(idx)} листов, "
          f"пустых: {sum(1 for p in pages if p.get('empty'))}")
    print(f"Записано: {d['work']}/pages.jsonl")
    print("Дальше: extract.py")


if __name__ == "__main__":
    main()
