#!/usr/bin/env python3
"""
Проекция карточек в формат загрузки.

Usage:
    python upload_projection.py --book books/<book-id> [--fields f1,f2,...] [--jsonl]

Внутреннее представление богаче загрузочного (§3.4). Поля, которых сейчас
не принимает приёмник, из корпуса не выбрасываются: они остаются в
output/cards.jsonl, а сюда попадает только проекция. Скрипт печатает,
что именно осталось за бортом, чтобы это было видимым решением, а не
незаметной потерей.

Отказ выгружать при непройденном QA — намеренный: карточки без отчёта
не выгружаются никогда (§22).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipelib as P

DEFAULT_FIELDS = [
    "id", "external_id", "book_id", "unit_type", "unit_number", "address", "citation",
    "text", "hierarchy", "page_start", "page_end",
    # Страница печатного издания — то единственное, что вправе попасть в
    # чужую сноску. page_start/page_end — страницы ФАЙЛА, и они с ней не
    # совпадают: у Snell's Equity para. 3-030 это 60–61 против 44–45 в книге.
    "printed_page_start", "printed_page_end",
    "footnotes", "statutory_refs",
    "cross_refs", "jurisdiction", "language", "source", "institute",
    "source_sha256", "profile", "chunk_version",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--fields", help="список полей через запятую")
    ap.add_argument("--jsonl", action="store_true", help="выгрузка построчно, а не одним массивом")
    ap.add_argument("--force", action="store_true", help="выгрузить вопреки непройденному QA")
    a = ap.parse_args()

    d = P.book_dirs(a.book)
    qa_path = os.path.join(d["report"], "qa.json")
    if not os.path.exists(qa_path):
        sys.exit("Нет report/qa.json. Отчёт о качестве обязателен до выгрузки (§14).")
    qa = json.load(open(qa_path, encoding="utf-8"))
    if qa.get("stops") and not a.force:
        print("QA не пройден:")
        for s in qa["stops"]:
            print(f"  - {s}")
        sys.exit("Выгрузка отменена. Разбираться с причиной, а не запускать с --force.")

    cards = P.read_jsonl(os.path.join(d["output"], "cards.jsonl"))
    fields = [f.strip() for f in a.fields.split(",")] if a.fields else DEFAULT_FIELDS
    dropped = sorted({k for c in cards for k in c} - set(fields))
    out = [{k: c.get(k) for k in fields} for c in cards]

    path = os.path.join(d["output"], "upload.jsonl" if a.jsonl else "upload.json")
    if a.jsonl:
        P.write_jsonl(path, out)
    else:
        P.write_json(path, out)

    print(f"Выгрузка: {len(out)} карточек → {path}")
    print(f"Полей в проекции: {len(fields)}")
    if dropped:
        print("Остались только во внутреннем представлении (это нормально, но должно быть "
              "видно): " + ", ".join(dropped))
    if qa.get("stops"):
        print("\nВНИМАНИЕ: выгружено с --force при непройденном QA. Записать это решение "
              "в docs/decisions.md.")


if __name__ == "__main__":
    main()
