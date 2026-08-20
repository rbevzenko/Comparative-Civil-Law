#!/usr/bin/env python3
"""Разбор номеров сносок под конвенцию этого издания.

    python scripts/fix_footnote_markers.py --book <каталог> [--dry-run]

Запускать ПОСЛЕ pages_digital.py и ДО extract.py: скрипт переписывает поле
`notes` в work/pages.jsonl, а раскладывать сноски по единицам будет сам
пайплайн — у него для этого есть офсеты, которых здесь нет.

Пайплайн ждёт знак сноски со скобкой или точкой («29)», «29.»), потому что
так набирают в большинстве книг. Verlag Österreich ставит голое число:

    29 DazunäherKodekinKonecny,Insolvenz-Forum2003,19.

Из-за этого ни один знак не читается, и вся полоса сносок страницы ложится
одним блоком без номера, а при загрузке такие сноски отсеиваются: в схеме
приёмника номер обязателен и целочисленный. У Insolvenzordnung² так терялось
3175 блоков из 3290, у Iro, Sachenrecht — 226 из 255.

Голое число само по себе слишком слабый признак: австрийские сноски набиты
номерами дел вида «5 Ob 142/68» и «3 Ob 627/82», и они начинают строку
ровно так же. Поэтому номер принимается только если он БОЛЬШЕ предыдущего
принятого на этой же странице: нумерация сносок возрастает, а номер дела
попадает в диапазон случайно и вниз. Первый номер страницы принимается,
только если строка не похожа на продолжение (не начинается с номера дела
вида «5 Ob …»).

Голое число можно спутать не только с номером дела. При четырёхзначной
нумерации (`--max-digits 4`) знаком сноски становится год в скобках:
«(2007) Ch.1.» — продолжение ссылки, а читается как сноска 2007. Против
этого два средства. `--marker dot` оставляет только ту форму знака, которой
книга пользуется на самом деле (у выгрузок Westlaw это «29.»), и заодно
отключает разбор голого числа: на живом прогоне Chitty vol.1 голое число
давало 883 ложные сноски из 19 523 — годы из перенесённых ссылок. `--max-step`
ограничивает шаг вперёд: номер сноски растёт на единицу и перезапускается с
1 в новой главе, а год прыгает на сотни. Счётчик при этом ведётся сквозь
полосы, а не с нуля на каждой: сноска 172 стоит на той полосе, где кончилась
171, и сравнивать её не с чем, если счётчик сбросить.

Сноска, начатая внизу одной полосы и продолженная вверху следующей, своего
номера на второй полосе не имеет и иметь не может. Такой хвост приписывается
к последней нумерованной сноске предыдущей полосы: иначе он остаётся блоком
без номера, а при загрузке блоки без номера отсеиваются — в схеме приёмника
номер обязателен. У Posch, IPR⁵ так висело 26 хвостов из 27 безномерных
блоков.
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

# «29 Dazu näher …» — знак и сразу текст.
BARE = re.compile(r"^(\d{1,3})\s+(?=\S)")
# Те же три правила под нумерацию длиннее трёх знаков: у выгрузок Westlaw
# сноски нумеруются сквозняком по тому и доходят до «1449.».
# «5 Ob 142/68», «3 Ob 627/82» — номер дела, а не знак сноски. Отделения
# суда мало: «103 Ob die Rechtswahl wirksam ist…» — это сноска 103, начатая
# с немецкого «ob» (ли), и без требования цифры после отделения она теряется.
CASE = re.compile(r"^\d{1,3}\s+(?:Ob|Ob[AS]|Präs|Nc|Fsc|Ds|Nd)\s+\d")
# Знак верхним индексом мог уехать на свою строку.
LONE = re.compile(r"^[\(\[]?(\d{1,3})[\)\].]?$")
# Штатные знаки со скобкой/точкой — их пайплайн читает и сам.
PUNCT = re.compile(r"^(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[\).])\s+(?=\S)")


def widen(digits):
    """Те же правила под номер сноски длиной до `digits` знаков."""
    global BARE, CASE, LONE, PUNCT, DIGITS
    DIGITS = digits
    d = "{1,%d}" % digits
    BARE = re.compile(r"^(\d%s)\s+(?=\S)" % d)
    CASE = re.compile(r"^\d%s\s+(?:Ob|Ob[AS]|Präs|Nc|Fsc|Ds|Nd)\s+\d" % d)
    LONE = re.compile(r"^[\(\[]?(\d%s)[\)\].]?$" % d)
    PUNCT = re.compile(r"^(?:\((\d%s)\)|\[(\d%s)\]|(\d%s)[\).])\s+(?=\S)" % (d, d, d))


MARKER_FORMS = {"any", "dot", "paren", "bracket"}


DIGITS = 3


def punct_form(s, form):
    """Знак сноски выбранной формы: «(29)», «[29]», «29.»."""
    d = "{1,%d}" % DIGITS
    if form in ("any", "paren"):
        m = re.match(r"^\((\d%s)\)\s+(?=\S)" % d, s)
        if m:
            return int(m.group(1)), m.end()
    if form in ("any", "bracket"):
        m = re.match(r"^\[(\d%s)\]\s+(?=\S)" % d, s)
        if m:
            return int(m.group(1)), m.end()
    if form in ("any", "dot"):
        tail = r"[\).]" if form == "any" else r"\."
        m = re.match(r"^(\d%s)%s\s+(?=\S)" % (d, tail), s)
        if m:
            return int(m.group(1)), m.end()
    return None, None


def parse_page(note_lines, page, form="any", max_step=0, last=0):
    notes, cur, pending = [], None, None

    def close():
        nonlocal cur
        if cur:
            notes.append(cur)
            cur = None

    # Номера, которые вообще встречаются на этой полосе: по ним проверяется
    # перезапуск нумерации.
    page_nums = set()
    for ln in note_lines:
        t = (ln["text"] or "").strip()
        c, _ = punct_form(t, form)
        if c is None:
            m = BARE.match(t)
            c = int(m.group(1)) if m and not CASE.match(t) else None
        if c is not None:
            page_nums.add(c)

    def plausible(cand):
        if max_step <= 0:
            return cand > last
        if last < cand <= last + max_step:
            return True
        # Нумерация сносок перезапускается в новой главе, и первая
        # разобранная полоса новой главы не обязана начинаться с единицы:
        # у Megarry & Wade сноски 1–3 второй главы стоят на её первой полосе,
        # где блока сносок нет вовсе, и разбор начинается с четвёртой.
        # Признак перезапуска — номер МЕНЬШЕ счётчика, за которым на этой же
        # полосе идёт следующий по порядку. Одинокое число (номер дела, год)
        # такой пары не имеет и счётчик не сбрасывает.
        return cand < last and (cand + 1) in page_nums

    for ln in note_lines:
        s = ln["text"].strip()
        if not s:
            continue

        m = LONE.match(s)
        if m and (max_step <= 0 or plausible(int(m.group(1)))):
            close()
            pending = int(m.group(1))
            continue

        num = None
        cand, end = punct_form(s, form)
        if cand is not None and (max_step <= 0 or plausible(cand)):
            num, rest = cand, s[end:].strip()
        elif form == "any":
            # Голое число принимается только тогда, когда форма знака заранее
            # не названа. Если книга ставит знак со скобкой или точкой (это и
            # говорит --marker), голое число в начале строки — продолжение
            # ссылки: «…Regulations 2004 (SI 2004/2095)…», перенесённое так,
            # что строка начинается с года.
            m = BARE.match(s)
            if m and not CASE.match(s):
                cand = int(m.group(1))
                if plausible(cand):
                    num, rest = cand, s[m.end():].strip()

        if num is not None:
            close()
            cur = {"number": num, "text": rest, "page": page}
            # Счётчик не опускается: ложный мелкий номер иначе занижает
            # планку и следующие настоящие номера отвергаются как «слишком
            # далёкие вперёд».
            last, pending = max(last, num), None
        elif pending is not None:
            close()
            cur = {"number": pending, "text": s, "page": page}
            last, pending = max(last, pending), None
        elif cur:
            cur["text"] += " " + s
        else:
            # Хвост сноски с предыдущей страницы: номера у него нет и быть
            # не может, но терять текст нельзя.
            cur = {"number": None, "page": page, "carried": True, "text": s}
    close()
    return notes


def repair_sequence(pages, max_step):
    """Снятие ложного знака сноски по ряду номеров.

    Номер дела или год, оказавшийся в начале перенесённой строки, читается
    как знак сноски и с точкой: «…[2014] EWCA Civ 75. [2014] 1 C.L.C. 113…».
    Отличить его от настоящего знака по виду строки нельзя — отличает ряд:
    после ложного знака нумерация продолжается с того места, где была, а не
    с него. Такая сноска приписывается обратно к предыдущей вместе со своим
    числом, как и была напечатана.
    """
    flat = [(pg, n) for pg in pages for n in (pg.get("notes") or [])]
    numbered = [(k, n) for k, (_, n) in enumerate(flat) if n.get("number") is not None]
    drop, last, fixed = set(), 0, 0

    def ok(num):
        return last == 0 or num == 1 or last < num <= last + max_step

    for i, (k, n) in enumerate(numbered):
        num = n["number"]
        if ok(num):
            last = num
            continue
        nxt = numbered[i + 1][1]["number"] if i + 1 < len(numbered) else None
        if nxt is not None and ok(nxt) and nxt != 1:
            host = next((flat[j][1] for j in range(k - 1, -1, -1) if j not in drop), None)
            if host is not None:
                host["text"] = f"{host.get('text', '')} {num}. {n.get('text', '')}".strip()
                drop.add(k)
                fixed += 1
                continue
        last = num

    if drop:
        seen = 0
        for pg in pages:
            notes = pg.get("notes") or []
            if not notes:
                continue
            pg["notes"] = [n for j, n in enumerate(notes, start=seen) if j not in drop]
            seen += len(notes)
    return fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--max-digits", type=int, default=3,
                    help="сколько знаков может быть в номере сноски")
    ap.add_argument("--marker", default="any", choices=sorted(MARKER_FORMS),
                    help="форма знака сноски: dot «29.», paren «(29)», bracket «[29]»")
    ap.add_argument("--max-step", type=int, default=0,
                    help="на сколько номер сноски вправе обогнать предыдущий (0 — без ограничения)")
    ap.add_argument("--repair-sequence", type=int, default=0, metavar="MAXSTEP",
                    help="снять ложный знак, если следующая сноска продолжает ряд (0 — не чинить)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.max_digits != 3:
        widen(a.max_digits)

    path = os.path.join(a.book, "work", "pages.jsonl")
    before = after = pages_touched = unnumbered = carried_merged = carry = 0
    out = []
    sample = []

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            old = p.get("notes") or []
            before += len(old)
            # Поле notes ВСЕГДА пересобирается из note_lines, даже когда их
            # не осталось. Иначе на полосе, у которой inline_superscripts.py
            # забрал из аппарата одни знаки сносок, остаётся прежний разбор:
            # блок «1 2 3» без номера, сделанный ещё в pages_digital. У
            # Treitel так висело 573 блока из 3907.
            new = parse_page(p["note_lines"], p.get("printed_page") or p["pdf_page"],
                             a.marker, a.max_step, carry) if p.get("note_lines") else []
            nums = [n["number"] for n in new if n.get("number") is not None]
            carry = nums[-1] if nums else carry
            if new:
                if len(sample) < 3 and len(new) > 2:
                    sample.append((p["pdf_page"], old, new))
                pages_touched += 1
            p["notes"] = new
            out.append(p)

    # Хвост сноски с предыдущей полосы: номера у него нет, приписываем к
    # последней нумерованной сноске той полосы, где сноска началась.
    for prev, cur in zip(out, out[1:]):
        notes = cur.get("notes") or []
        if not notes or not notes[0].get("carried"):
            continue
        host = next((n for n in reversed(prev.get("notes") or [])
                     if n.get("number") is not None), None)
        if host is None:
            continue
        host["text"] = (host.get("text", "") + " " + notes[0].get("text", "")).strip()
        cur["notes"] = notes[1:]
        carried_merged += 1

    if a.repair_sequence:
        repaired = repair_sequence(out, a.repair_sequence)
        print(f"ложных знаков снято по ряду: {repaired}")

    for p in out:
        after += len(p.get("notes") or [])
        unnumbered += sum(1 for n in (p.get("notes") or []) if n.get("number") is None)

    print(f"страниц со сносками: {pages_touched}")
    print(f"хвостов с предыдущей полосы прирощено: {carried_merged}")
    print(f"сносок было: {before} → стало: {after}, из них без номера: {unnumbered}")
    for pg, old, new in sample:
        print(f"\n  f{pg} было {len(old)}: {json.dumps(old[:1], ensure_ascii=False)[:150]}")
        print(f"       стало {len(new)}:")
        for n in new[:4]:
            print(f"         {n['number']}: {n['text'][:70]}")

    if a.dry_run:
        print("\ndry-run: файл не тронут")
        return
    with open(path, "w", encoding="utf-8") as fh:
        for p in out:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nЗаписано: {path}")
    print("Дальше: extract.py заново — он разложит сноски по единицам сам")


if __name__ == "__main__":
    main()
