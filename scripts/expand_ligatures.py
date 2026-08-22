#!/usr/bin/env python3
"""Разложение типографских лигатур на обычные буквы.

    python scripts/expand_ligatures.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

Не путать с fix_broken_ligatures.py: там глиф лигатуры НЕ размечен и слово
рвётся на его месте («at fi rst»). Здесь наоборот — глиф размечен честно, и
в текст приезжает единый знак ﬁ (U+FB01), ﬂ, ﬀ, ﬃ, ﬄ, ﬅ, ﬆ.

Слово при этом выглядит правильно и читается глазом без запинки, но для
поиска это ДРУГОЕ слово: «justiﬁent» с лигатурой не находится по запросу
«justifient». У Симлера, Les sûretés таких знаков 3276 на книгу.

Полнотекстовый поиск сервиса нормализацию Unicode не делает, поэтому
раскладывать надо до нарезки, чтобы разложенным был и текст карточки, и
эмбеддинг.
"""

import argparse
import json
import os

LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}


def expand(text):
    for k, v in LIGATURES.items():
        if k in text:
            text = text.replace(k, v)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    pages = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    hits = 0
    sample = None
    for pg in pages:
        for key in ("lines", "note_lines"):
            for ln in pg.get(key) or []:
                for field in (ln, *(ln.get("words") or [])):
                    t = field.get("text") or ""
                    new = expand(t)
                    if new != t:
                        if sample is None and field is ln:
                            sample = (t[:70], new[:70])
                        field["text"] = new
                        hits += 1

    print(f"строк с лигатурами: {hits}")
    if sample:
        print(f"  было:  {sample[0]!r}")
        print(f"  стало: {sample[1]!r}")
    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"записано: {path}")


if __name__ == "__main__":
    main()
