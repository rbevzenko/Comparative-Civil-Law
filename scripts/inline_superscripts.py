#!/usr/bin/env python3
"""Возврат знаков сноски, уехавших на отдельную строку, в свою строку тела.

    python scripts/inline_superscripts.py --book <каталог> [--size-max 7] [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

pipelib.cluster_lines приклеивает верхний индекс к строке тела только тогда,
когда он стоит С КРАЮ строки: правило `beside` требует, чтобы знак не
накладывался на полосу слов по горизонтали, иначе блок сносок посимвольно
сплетается с последней строкой тела. Знак в СЕРЕДИНЕ строки («ancestor,¹⁷²
or of the next-of-kin…») под это правило не подходит и остаётся отдельной
строкой из одних цифр.

У Snell's Equity таких строк примерно по пять на полосу: знак сноски там
ставится после запятой в середине фразы, а не в конце предложения. В book.txt
они превращаются в разрывы («…of a liv- 172 ing person»), и текст карточки
рвётся ровно там, где чаще всего стоит ссылка на прецедент.

Скрипт находит строку, состоящую только из чисел и набранную мелким кеглем,
подбирает ей строку-хозяина по вертикальному перекрытию и вставляет каждое
число обратно на своё место по x. Число приклеивается к предыдущему слову
без пробела, если зазор мал, — так же, как это делает chars_to_lines с теми
знаками, что стоят с краю («prevails.160»).

Строка-хозяин ищется только среди строк ТЕЛА полосы, а сам знак берётся и
из тела, и из note_lines. Второе обязательно: split_footnotes решает по
кеглю и полосе, и знак сноски в нижней половине полосы («168» на 0.50
высоты, кегль 6) уезжает в блок сносок. Там он читается как номер сноски,
сбивает счётчик fix_footnote_markers.py, и вся полоса сносок ложится одним
блоком — у f61 так терялось 10 сносок из 12. Знак без строки-хозяина
остаётся там, где был: в самом блоке сносок верхние индексы настоящие.
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

ONLY_NUMBERS = re.compile(r"^[\d\s]+$")


def is_marker_line(ln, size_max):
    s = (ln.get("text") or "").strip()
    if not s or not ONLY_NUMBERS.match(s):
        return False
    if ln.get("size") is None or ln["size"] > size_max:
        return False
    return all(re.fullmatch(r"\d{1,3}", w["text"]) for w in ln.get("words") or [])


def overlap(a, b):
    return min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])


def rebuild(line, glue_gap=1.8):
    words = sorted(line["words"], key=lambda w: w["x0"])
    parts = []
    for w in words:
        if parts and w.get("_marker") and w["x0"] - parts[-1][1] <= glue_gap:
            parts[-1] = (parts[-1][0] + w["text"], w["x1"])
        else:
            parts.append((w["text"], w["x1"]))
    line["words"] = words
    line["text"] = " ".join(t for t, _ in parts).strip()
    line["x0"] = min(w["x0"] for w in words)
    line["x1"] = max(w["x1"] for w in words)
    for w in words:
        w.pop("_marker", None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--size-max", type=float, default=7.0)
    ap.add_argument("--host-notes", action="store_true",
                    help="искать строку-хозяина и среди строк аппарата")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    moved = dropped = touched = 0
    sample = []
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in fh:
            pg = json.loads(row)
            lines = pg.get("lines") or []
            notes = pg.get("note_lines") or []
            markers = [ln for ln in lines + notes if is_marker_line(ln, a.size_max)]
            if not markers:
                out.append(pg)
                continue
            body = [ln for ln in lines if not is_marker_line(ln, a.size_max)]
            # У Megarry & Wade номер сноски в самом аппарате набран двумя
            # кеглями: «27» — это «2» кеглем 8 и «7» кеглем 4.4, и кластеризация
            # разводит их по разным строкам. Без --host-notes хвост номера
            # некуда вернуть, и сноска 27 читается как сноска 2.
            hosts = body
            if a.host_notes:
                hosts = body + [ln for ln in notes if not is_marker_line(ln, a.size_max)]
            pulled = set()
            changed = set()
            for ml in markers:
                # Половина высоты знака: случайного касания рамок мало,
                # знак должен стоять ВНУТРИ строки-хозяина по вертикали.
                need = 0.5 * max(1.0, ml["bottom"] - ml["top"])
                cand = [(overlap(ml, b), -abs(ml["x0"] - b["x0"]), i)
                        for i, b in enumerate(hosts) if overlap(ml, b) >= need]
                if not cand:
                    dropped += len(ml.get("words") or [])
                    continue
                host = hosts[max(cand)[2]]
                before = host["text"]
                for w in ml["words"]:
                    host["words"].append(dict(w, _marker=True))
                rebuild(host)
                moved += len(ml["words"])
                pulled.add(id(ml))
                changed.add(id(host))
                if len(sample) < 6:
                    sample.append((pg["pdf_page"], before[:60], host["text"][:70]))
            if changed:
                touched += 1
            pg["lines"] = body
            if notes:
                pg["note_lines"] = [ln for ln in notes if id(ln) not in pulled]
            out.append(pg)

    print(f"полос затронуто: {touched}")
    print(f"знаков возвращено в строку: {moved}, оставлено на месте (нет хозяина): {dropped}")
    for pgno, before, after in sample:
        print(f"  f{pgno}: {before!r}\n      → {after!r}")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for pg in out:
            fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")


if __name__ == "__main__":
    main()
