#!/usr/bin/env python3
"""Перенос составного маргинального номера с правого поля в начало строки.

    python scripts/move_margin_numbers.py --book <каталог> --pattern '^\\d{1,2}-\\d{3}$' \
        --min-x 380 [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Штатный режим `margin` в extract.py берёт с поля только ГОЛОЕ число:
pull_margin_tokens проверяет токен через `re.fullmatch(r"\\d{1,4}", s)`.
Составной номер («3-031» у Snell's Equity, где 3 — глава, а 031 — абзац
внутри главы) под это не подходит, и режим margin теряет все адреса.

Разворот у таких книг устроен так, что номер стоит на ВНЕШНЕМ поле и меняет
сторону: на одной странице он и так первое слово строки, и flow-режим читает
его сам, а на другой — последнее слово, за правым краем полосы набора.
Скрипт переносит второй случай в начало строки, и дальше обе стороны
разбираются одним flow-паттерном.

Переносится только ПОСЛЕДНЕЕ слово строки и только если оно стоит правее
--min-x. Порог важен: тем же паттерном набраны перекрёстные ссылки в тексте
(«see para. 3-042») и строки постраничного оглавления главы с отточием, но
они лежат внутри полосы набора, а поле начинается за её правым краем.

Флаг `--from-text` включает второй способ — для сканов, где геометрии взять
не за что: номер снимается с конца ТЕКСТА строки, а свой он или чужой,
решает СЧЁТ. Подробности в docstring `from_text`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import os
import re


def from_text(a):
    """Номер снимается с конца ТЕКСТА строки, а свой он или чужой — решает счёт.

    Геометрия работает не всегда. У Hanbury & Martin, Modern Equity (скан)
    правый край строк тела распадается на два скопления (430 и 470–480 pt):
    полосы сняты с разным масштабом. Номер как последнее слово начинается на
    400–440 pt, диапазоны ПЕРЕСЕКАЮТСЯ, и порога --min-x не существует.
    Вдобавок `_space_gap` на большинстве полос не находит границ слов, и вся
    строка становится ОДНИМ словом — последнего слова, за которое можно
    взяться, там просто нет.

    Зато номер абзаца по книге ВОЗРАСТАЕТ, а перекрёстная ссылка («see para.
    3-042») и строка оглавления главы — нет. Поэтому из всех кандидатов
    берётся САМАЯ ДЛИННАЯ ВОЗРАСТАЮЩАЯ ПОДПОСЛЕДОВАТЕЛЬНОСТЬ, и переносятся
    только вошедшие в неё.

    Жадный проход слева направо тут не годится: одна строка оглавления в
    начале главы («11. The Recognition of Trusts Act 1987  1-052») задирает
    счётчик, и все настоящие 1-001…1-051 после неё отвергаются. У Hanbury
    жадный проход принимал 27 номеров из 1039, подпоследовательность — 940.
    """
    rx = re.compile(a.pattern)
    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8")]

    cands = []          # (ключ, ссылка на строку, совпадение) в порядке книги
    already = 0
    for pg in pages:
        for ln in pg.get("lines") or []:
            t = (ln.get("text") or "").rstrip()
            head = rx.match(t.lstrip())
            if head:
                already += 1
                cands.append(((int(head.group(1)), int(head.group(2))), None, None, pg["pdf_page"]))
                continue
            m = rx.search(t)
            if m and m.end() == len(t):
                cands.append(((int(m.group(1)), int(m.group(2))), ln, m, pg["pdf_page"]))

    # Самая длинная строго возрастающая подпоследовательность по (глава, номер).
    import bisect
    tails, prev, idx = [], [None] * len(cands), []
    for i, c in enumerate(cands):
        k = c[0]
        j = bisect.bisect_left([cands[t][0] for t in idx], k)
        prev[i] = idx[j - 1] if j else None
        if j == len(idx):
            idx.append(i)
        else:
            idx[j] = i
    keep = set()
    cur = idx[-1] if idx else None
    while cur is not None:
        keep.add(cur)
        cur = prev[cur]

    moved = rejected = 0
    sample = []
    for i, (key, ln, m, pno) in enumerate(cands):
        if ln is None:
            continue
        if i not in keep:
            rejected += 1
            continue
        t = (ln.get("text") or "").rstrip()
        before = t
        if not a.dry_run:
            ln["text"] = (m.group(0).strip() + " " + t[:m.start()].strip()).strip()
        moved += 1
        if len(sample) < 5:
            sample.append((pno, before[-60:], ln["text"][:70] if not a.dry_run else "—"))

    print(f"перенесено с конца строки: {moved}")
    print(f"уже стояло первым (левое поле): {already}")
    print(f"отклонено как не продолжающее счёт: {rejected}")
    for pgno, before, after in sample:
        print(f"  f{pgno}: …{before!r}\n      → {after!r}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in pages:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pattern", required=True, help="полное совпадение со словом на поле")
    ap.add_argument("--min-x", type=float, help="левая граница поля в пунктах")
    ap.add_argument("--from-text", action="store_true",
                    help="искать номер в КОНЦЕ ТЕКСТА строки, а не в последнем слове, "
                         "и отличать его от перекрёстной ссылки по счёту, а не по полю")
    ap.add_argument("--max-step", type=int, default=3,
                    help="--from-text: насколько номер вправе обгонять предыдущий")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.from_text and a.min_x is None:
        raise SystemExit("нужен либо --min-x, либо --from-text")
    if a.from_text:
        return from_text(a)

    rx = re.compile(a.pattern)
    path = os.path.join(a.book, "work", "pages.jsonl")
    moved = already = 0
    sample = []
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in fh:
            pg = json.loads(row)
            for ln in pg.get("lines") or []:
                words = ln.get("words") or []
                if not words:
                    continue
                if rx.match(words[0]["text"].strip()):
                    already += 1
                    continue
                last = words[-1]
                if not rx.match(last["text"].strip()) or last["x0"] < a.min_x:
                    continue
                rest = words[:-1]
                if not rest:
                    continue
                ln["words"] = [last] + rest
                before = ln["text"]
                ln["text"] = (last["text"] + " " + " ".join(w["text"] for w in rest)).strip()
                ln["x0"] = min(w["x0"] for w in ln["words"])
                ln["x1"] = max(w["x1"] for w in ln["words"])
                moved += 1
                if len(sample) < 5:
                    sample.append((pg["pdf_page"], before[-60:], ln["text"][:70]))
            out.append(pg)

    print(f"перенесено с правого поля: {moved}")
    print(f"уже стояло первым словом (левое поле): {already}")
    for pgno, before, after in sample:
        print(f"  f{pgno}: …{before!r}\n      → {after!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in out:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
