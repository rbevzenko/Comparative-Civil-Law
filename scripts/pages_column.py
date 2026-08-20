#!/usr/bin/env python3
"""Одна колонка двуязычной полосы → модель страницы.

    python scripts/pages_column.py книга.pdf --book books/<id> --profile … \
        --split 300 --column right [--pages 14-45] [--skip-done]

Обёртка вокруг `pages_digital.py` для бельгийских парламентских документов
(Doc. Chambre). Текст там набран в две колонки: слева нидерландский, справа
французский, строка к строке. Обычная сборка строк идёт через всю полосу и
склеивает два языка в одну строку —

    Persoonlijke zekerheden, zoals de borgtocht, spe- Les sûretés personnelles, tel le cautionnement, jouent

— то есть непригодно ни для чтения, ни для эмбеддинга.

Скрипт отбирает символы одной стороны от `--split` и передаёт их той же
сборке, что и обычная ветка A: дальше всё как всегда — колонцифра, мусор,
строки тела. Отдельная колонка того же документа берётся вторым прогоном в
другой каталог книги.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.claude/skills/synced/complaw-corpus/scripts")
sys.path.insert(0, SKILL)
import pipelib as P
import pages_digital as PD

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")


# Порядковый суффикс французского числительного набран верхним индексом и
# приходит ОТДЕЛЬНОЙ строкой, причём выше той, к которой относится:
#
#     …de l’exis-
#     er
#     tence de l’obligation garantie (alinéa 1 ).
#
# Поставить его на место нельзя — он висит не над своим числом, а над концом
# предыдущей строки. Поэтому такие строки снимаются: «alinéa 1» вместо
# «alinéa 1er» смысла не теряет, а «er» посреди фразы делает карточку
# нечитаемой.
ORDINAL = re.compile(r"^(?:er|re|ère|ème|es|e|°|ers)$")


def drop_ordinals(page):
    before = len(page["lines"])
    page["lines"] = [ln for ln in page["lines"] if not ORDINAL.match(ln["text"].strip())]
    return before - len(page["lines"])


class Column:
    """Страница, суженная до одной колонки: то, что нужно build_page."""

    def __init__(self, page, lo, hi):
        self.height, self.width = float(page.height), float(page.width)
        self.chars = [c for c in page.chars if lo <= c["x0"] < hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--book", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--split", type=float, required=True, help="граница колонок по x")
    ap.add_argument("--column", choices=["left", "right"], required=True)
    ap.add_argument("--pages")
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()

    prof = P.load_profile(a.profile)
    junk_rx = P.compile_patterns(prof.get("junk", {}).get("patterns"))
    d = P.book_dirs(a.book)
    cache = os.path.join(d["cache"], "pages")
    os.makedirs(cache, exist_ok=True)
    lo, hi = (0.0, a.split) if a.column == "left" else (a.split, 10 ** 6)

    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        done = dropped = 0
        for i in idx:
            path = os.path.join(cache, f"page-{i + 1:05d}.json")
            if a.skip_done and os.path.exists(path):
                done += 1
                continue
            built = PD.build_page(Column(pdf.pages[i], lo, hi), i, prof, junk_rx)
            dropped += drop_ordinals(built)
            P.write_json(path, built)
            done += 1
            if done % 50 == 0:
                print(f"  полос разобрано: {done}/{len(idx)}", flush=True)

    import json as _json
    wanted = sorted({i + 1 for i in idx} | (
        {int(n[5:10]) for n in os.listdir(cache) if n.startswith("page-") and n.endswith(".json")}
        if a.skip_done else set()))
    pages = []
    for pno in wanted:
        path = os.path.join(cache, f"page-{pno:05d}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                pages.append(_json.load(fh))

    P.write_jsonl(os.path.join(d["work"], "pages.jsonl"), pages)
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf),
        "source_sha256": P.sha256_file(a.pdf),
        "branch": "A", "method": "digital",
        "profile": prof.get("id"),
        "column": a.column, "split_x": a.split,
        "pages_requested": len(idx), "pages_built": len(pages),
        "pages_empty": sum(1 for p in pages if p.get("empty")),
        "schema_version": P.SCHEMA_VERSION,
    })
    print(f"Полос в модели: {len(pages)}, пустых: {sum(1 for p in pages if p.get('empty'))}, "
          f"колонка: {a.column}")
    print(f"снято строк-суффиксов верхнего индекса: {dropped}")
    print(f"Записано: {d['work']}/pages.jsonl")
    print("Дальше: extract.py")


if __name__ == "__main__":
    main()
