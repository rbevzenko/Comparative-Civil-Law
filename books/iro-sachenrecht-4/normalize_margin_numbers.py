#!/usr/bin/env python3
"""Составной номер с внешнего поля — в начало своей строки.

    python normalize_margin_numbers.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py.

У этой книги номер единицы висит на ВНЕШНЕМ поле и потому меняет сторону на
развороте: на чётных страницах файла слева (x≈152), на нечётных справа
(x≈1540). Режим `margin` его не берёт — там номер обязан быть голым числом,
а здесь он составной и печатается слитно («1/16» = § 1 Rz 16). Режим `flow`
берёт только левую половину книги: он ищет номер в начале строки, а справа
номер стоит в конце.

Скрипт приводит обе стороны к одному виду: номер, стоящий ЗА полосой набора,
снимается со строки и приписывается к её началу. Дальше книга целиком идёт
режимом `flow`, и ничего больше в пайплайне менять не нужно.

Что именно считается номером на поле:

  * слово вида «1/16», «10/4», а также разорванное распознаванием «11 /16»;
  * стоящее ПЕРВЫМ словом строки левее полосы или ПОСЛЕДНИМ правее неё —
    число в середине строки это перекрёстная ссылка, а не номер единицы;
  * номер параграфа в пределах книги (§§ 1-17), иначе «266/12» из цитаты
    завело бы в корпус несуществующий раздел.

Полоса набора меряется по каждой странице отдельно и только по нечисловым
словам длинных строк: сам висячий номер иначе растягивает полосу на себя.
"""

import argparse
import json
import os
import re
import statistics

NUM = re.compile(r"^(\d{1,3})\s?/\s?(\d{1,3})$")
PAD = 8.0
# Снятый с поля номер отделяется от текста неразрывным пробелом. Это метка,
# а не косметика: строка, начинающаяся с «5/79 ff)», — это перенос
# перекрёстной ссылки, а не начало единицы, и без метки пайплайн заводит на
# ней карточку с чужим адресом. Обычного пробела в этой роли достаточно не
# будет, а U+00A0 в слое книги не встречается ни разу (проверено).
MARK = "\u00a0"
MAX_SECTION = 17          # §§ 1-17 по оглавлению книги


def body_edges(lines):
    left, right = [], []
    for ln in lines:
        words = [w for w in (ln.get("words") or []) if not NUM.match(w["text"].strip())]
        if len(ln["text"]) > 40 and words:
            left.append(min(w["x0"] for w in words))
            right.append(max(w["x1"] for w in words))
    if not left:
        return None
    return statistics.median(left), statistics.median(right)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = os.path.join(a.book, "work", "pages.jsonl")
    out, moved_left, moved_right, skipped = [], 0, 0, 0
    sample = []

    for line in open(path, encoding="utf-8"):
        page = json.loads(line)
        edges = body_edges(page["lines"])
        if edges is None:
            out.append(page)
            continue
        body_l, body_r = edges

        for ln in page["lines"]:
            words = sorted(ln.get("words") or [], key=lambda w: w["x0"])
            if not words:
                continue
            for where, w in (("left", words[0]), ("right", words[-1])):
                m = NUM.match(w["text"].strip())
                if not m or int(m.group(1)) > MAX_SECTION or int(m.group(1)) < 1:
                    continue
                outside = (w["x1"] <= body_l - PAD) if where == "left" else (w["x0"] >= body_r + PAD)
                if not outside:
                    skipped += 1
                    continue
                num = f"{int(m.group(1))}/{int(m.group(2))}"
                rest = [x for x in words if x is not w]
                ln["words"] = rest
                ln["text"] = (num + MARK + " ".join(x["text"] for x in rest)).strip()
                if rest:
                    ln["x0"] = min(x["x0"] for x in rest)
                    ln["x1"] = max(x["x1"] for x in rest)
                if where == "left":
                    moved_left += 1
                else:
                    moved_right += 1
                    if len(sample) < 3:
                        sample.append((page["pdf_page"], num, ln["text"][:64]))
                break
        out.append(page)

    print(f"номеров снято с поля: слева {moved_left}, справа {moved_right}, "
          f"всего {moved_left + moved_right}")
    print(f"похожих слов внутри полосы (перекрёстные ссылки, не тронуты): {skipped}")
    for pg, num, text in sample:
        print(f"  f{pg}: номер {num} с правого поля → «{text}…»")

    if a.dry_run:
        print("dry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for page in out:
            fh.write(json.dumps(page, ensure_ascii=False) + "\n")
    print(f"Записано: {path}")
    print("Дальше: extract.py")


if __name__ == "__main__":
    main()
