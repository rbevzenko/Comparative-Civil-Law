#!/usr/bin/env python3
"""Разбор распечатки beck-online на карточки «§ N Rn. M».

    python scripts/beck_extract.py --book books/<id> --pdf файл.pdf \
        [--pages 1-200] [--jurisdiction DE] [--dry-run]

ЗАЧЕМ ОТДЕЛЬНЫЙ РАЗБОРЩИК. Штатная ветка (pages_digital → extract) устроена
под бумажную книгу: колонцифра, поле с маргиналиями, аппарат сносок внизу
полосы. Распечатка beck-online — не книга. Это склейка ЗАДАНИЙ ПЕЧАТИ:

    шапка   BGB § 273 Zurückbehaltungsrecht Krüger Münchener Kommentar zum BGB
            10. Auflage 2025
    текст   …
    аппарат 9  BGHZ 41, 30 (35) = NJW 1964, 811; …
    ссылка  Zitiervorschläge:
            MüKoBGB/Krüger, 10. Aufl. 2025, BGB § 273 Rn. 9-12

Колонцифры нет вовсе, а номер Randnummer печатается на правом поле ТОЛЬКО
когда задание охватывает несколько номеров. Задание на один номер печатается
без него: номер известен лишь из строки «Zitiervorschläge». По выборке из
шестнадцати файлов МюКо доля страниц с напечатанным номером гуляет от 0,4%
до 5,5% длинных строк — то есть на части файлов резать по полю просто нечего.

Поэтому единицу задаёт САМО ЗАДАНИЕ ПЕЧАТИ, а поле — лишь уточняет:
  * есть напечатанные номера → текст задания режется по ним;
  * номеров нет, задание на один Rn → всё тело задания и есть этот Rn;
  * номеров нет, задание на диапазон → одна карточка на весь диапазон,
    и об этом печатается предупреждение: это потеря дробности, а не норма.

ГРАНИЦА ЗАДАНИЯ — строка «Zitiervorschläge». Она стоит в КОНЦЕ задания и
описывает то, что было НАД ней. Шапка для этого не годится: у коротких
заданий её нет вовсе (первое задание печатает Schrifttum и оглавление
параграфа, второе — сразу текст).

АППАРАТ отделяется не по высоте полосы и не по кеглю в одиночку, а по паре
признаков: номер сноски набран кеглем 8.4 в левой колонке (x0 ≈ 44), а её
текст — кеглем 10.5 с отступом (x0 ≈ 59). Отступ обязателен: в широкой
вёрстке (Schrifttum, оглавление) тело тоже начинается с x0 ≈ 44, и один
кегль их не разделяет.

Нумерация сносок сквозная ПО ПАРАГРАФУ, а не по странице, и аппарат стоит
в конце задания. Внутри задания сноска привязывается к карточке по знаку
в тексте, а не по полосе.
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"
sys.path.insert(0, SKILL)
import pipelib as P

try:
    import pdfplumber
except ImportError:
    sys.exit("Нужен pdfplumber: pip install pdfplumber")

LIG = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
                     "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st"})

# Строка «Zitiervorschläge» и сама ссылка. Длинная форма (с изданием и годом)
# нужна целиком: из неё берутся комментатор, издание, год, параграф и номера.
ZITIER = re.compile(r"^Zitiervorschl[aä]g(?:e)?:?$")
CITE_LONG = re.compile(
    r"^(?P<werk>[A-Za-zÄÖÜäöü]+)/(?P<bearb>[^,]{1,60}?),\s*"
    r"(?P<aufl>\d{1,2})\.\s*Aufl\.\s*(?P<year>\d{4}),\s*"
    r"(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*)\s*(?P<vor>Vor\s*)?§+\s*(?P<par>\d+[a-zä]?)"
    r"(?:\s*(?:und|bis|-|–)\s*§*\s*\d+[a-zä]?)?"
    # Уточнение внутри параграфа: «BGB § 309 Abs. 5 Rn. 1, 2». Это отдельная
    # единица комментария со своим счётом Randnummern, и без него Rn. 1
    # к § 309 Abs. 5 столкнётся с Rn. 1 к § 309 Abs. 1. У § 309 таких
    # подразделов тринадцать, и на них приходится 371 задание печати.
    r"(?P<qual>(?:\s*(?:Abs|Nr|S)\.\s*\d+[a-z]?)*)"
    r"(?:\s*Rn\.\s*(?P<rn>[\d\s\-–,]+))?\s*$")
CITE_SHORT = re.compile(r"^[A-Za-zÄÖÜäöü]+/[^,]{1,60}\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*\s*(Vor\s*)?§+\s*\d")

JUNK = [
    re.compile(r"-\s*beck-online\s*$"),
    # Водяной знак библиотеки приходит в двух видах — со сжатыми пробелами
    # («KopievonPeacePalaceLibrary») и с обычными. Пропустить второй значило
    # потерять и границу задания: строка «Zitiervorschläge» на этих полосах
    # разорвана концом полосы, а водяной знак стоит ровно в разрыве.
    re.compile(r"Kopie\s*von\s*Peace\s*Palace", re.I),
    re.compile(r"beck-online\s*DIE\s*DATENBANK", re.I),
    re.compile(r"Verlag\s*C\.H\.Beck\s*GmbH"),
    re.compile(r"^©\s"),
    re.compile(r"^https?://"),
    re.compile(r"Text-und-Data-Mining"),
    re.compile(r"^\d+\s*von\s*\d+\s"),
]

# Шапка задания печати. Она приходит то тремя строками в две колонки
# («BGB § 104 Spickhoff Münchener / Geschäftsunfähigkeit Kommentar zum BGB /
# 10. Auflage 2025»), то одной склеенной («BGB § 241 Pflichten aus dem
# Bachmann Münchener Kommentar zum Rn. 3, 4»). Общее у них — слово
# «Münchener» и номер издания.
HEAD_LINE = [
    re.compile(r"M[üu]nchener"),
    re.compile(r"^Kommentar zum BGB$"),
    re.compile(r"^\d{1,2}\.\s*Auflage\s*\d{4}$"),
]
# Хвост шапки, перенесённый на следующую строку: короткая строка,
# заканчивающаяся названием кодекса. Снимается ТОЛЬКО сразу за строкой шапки —
# сама по себе такая строка бывает и концом абзаца («… gilt § 242 BGB»).
HEAD_TAIL = re.compile(r"^.{0,50}\s(BGB|EGBGB|HGB)$")
# Номер сноски первым словом строки. Проверять это по СЛОВАМ нельзя: на части
# полос межсловные пробелы у́же порога, и вся строка приходит одним словом.
HANG = re.compile(r"^(\d{1,3})\s+(\S.*)$")

NUM_ONLY = re.compile(r"\d{1,4}")


def norm(s):
    return re.sub(r"\s+", " ", s.translate(LIG)).strip()


# Слово, разорванное переносом, для поиска — два разных слова. «konklu-\ndent»
# не найдётся ни по «konkludent», ни по одной из половин.
ELLIPSIS = {"und", "oder", "bzw", "sowie", "wie", "als", "noch", "aber", "bis",
            "statt", "ohne", "et", "ou", "ni"}
# Сокращения законов и судов: после них дефис в конце строки почти всегда
# настоящий («BGB-RGRK», «GmbHG-Kommentar»), а не перенос.
ABBREV = {"BGB", "EGBGB", "HGB", "ZPO", "StGB", "StPO", "InsO", "AktG", "GmbHG",
          "AGB", "AGBG", "GG", "UWG", "GWB", "VVG", "WEG", "GVG", "FamFG", "AGG",
          "RGRK", "NJW", "JZ", "JuS", "BGH", "BAG", "BVerfG", "OLG", "EU", "EG"}
HYPHEN = re.compile(r"(\w+)-\n(\w+)")


def join_hyphens(text):
    """Склеить слово, разорванное переносом в конце строки.

    Слово, разорванное переносом, для поиска — два разных слова: «konklu-\ndent»
    не найдётся ни по «konkludent», ни по одной из половин. Во французской
    части корпуса переносы остались как есть, и это её известный дефект;
    немецкую собираем уже без них.

    Не всякий дефис в конце строки — перенос. Он бывает знаком пропуска
    («Rechts- und Staatswissenschaft») и частью составного сокращения
    («BGB-RGRK»). Первое опознаётся по союзу в начале следующей строки,
    второе — по списку сокращений. Всё остальное склеивается, включая имена
    капителью, разорванные пополам: «WESTER-\nMANN» — это Вестерман, а не два
    слова.
    """
    def repl(m):
        head, tail = m.group(1), m.group(2)
        if tail.split()[0].strip(".,;:").lower() in ELLIPSIS:
            return m.group(0)
        if head in ABBREV:
            return m.group(0)
        return head + tail
    return HYPHEN.sub(repl, text)


def splice_patches(lines, patches):
    """Вернуть в строки слова, нарисованные в PDF контурами.

    Слово распознавания встаёт в ту строку, с которой пересекается по
    вертикали, и на своё место по горизонтали. Слова, которым строки не
    нашлось, — это целиком контурная строка (полужирный заголовок или
    Randnummer у самого края); они собираются в новую строку по высоте.
    """
    if not patches:
        return lines
    leftover = []
    for pt in patches:
        cy = (pt["top"] + pt["bottom"]) / 2
        best, overlap = None, 0.0
        for ln in lines:
            top, bot = ln["top"] - 2, ln["bottom"] + 2
            if not top <= cy <= bot:
                continue
            o = min(bot, pt["bottom"]) - max(top, pt["top"])
            if o > overlap:
                best, overlap = ln, o
        if best is None:
            leftover.append(pt)
            continue
        w = {"text": pt["text"], "x0": pt["x0"], "x1": pt["x1"],
             "top": pt["top"], "bottom": pt["bottom"], "size": best.get("size")}
        best["words"] = sorted(best["words"] + [w], key=lambda x: x["x0"])
        best["text"] = norm(" ".join(x["text"] for x in best["words"]))
        best["x0"] = min(best["x0"], w["x0"])
        best["x1"] = max(best["x1"], w["x1"])

    rows = []
    for pt in sorted(leftover, key=lambda q: (q["top"], q["x0"])):
        if rows and abs(rows[-1][0]["top"] - pt["top"]) <= 4:
            rows[-1].append(pt)
        else:
            rows.append([pt])
    for row in rows:
        words = [{"text": q["text"], "x0": q["x0"], "x1": q["x1"],
                  "top": q["top"], "bottom": q["bottom"],
                  "size": round(min(20.0, max(7.0, q["bottom"] - q["top"])), 1)} for q in row]
        ln = P._mk_line(sorted(words, key=lambda x: x["x0"]),
                        size=statistics.median([w["size"] for w in words]))
        ln["text"] = norm(ln["text"])
        if ln["text"]:
            lines.append(ln)
    return sorted(lines, key=lambda l: (round(l["top"], 1), l["x0"]))


def read_lines(pdf, idx, patches=None):
    """Строки всех полос подряд, с координатами и номером полосы файла."""
    out = []
    for i in idx:
        page = pdf.pages[i]
        lines = [ln for ln in P.chars_to_lines(page.chars) if norm(ln["text"])]
        for ln in lines:
            ln["text"] = norm(ln["text"])
        lines = splice_patches(lines, (patches or {}).get(str(i + 1)))
        for ln in lines:
            ln["pdf_page"] = i + 1
            ln["height"] = float(page.height)
            ln["width"] = float(page.width)
            if ln["text"]:
                out.append(ln)
        page.flush_cache()
        page.get_textmap.cache_clear()
    return out


def split_jobs(lines):
    """Разрезать поток строк по блокам «Zitiervorschläge».

    Блок стоит в конце задания, поэтому всё, что накопилось до него, — тело
    этого задания. Хвост файла после последнего блока (у части файлов
    последнее задание обрывается) отдаётся отдельным заданием без ссылки.
    """
    jobs, cur = [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ZITIER.match(ln["text"]):
            # Блок ссылки разрывается концом полосы: короткая форма остаётся
            # внизу, между ними встают адрес печати и колонтитул следующей
            # полосы, и только потом идёт длинная форма. Поэтому мусорные
            # строки внутри блока пропускаются, а не обрывают его.
            cite, j = None, i + 1
            while j < len(lines) and j <= i + 6:
                t = lines[j]["text"]
                m = CITE_LONG.match(t)
                if m:
                    cite = m.groupdict()
                elif not CITE_SHORT.match(t) and not any(rx.search(t) for rx in JUNK):
                    break
                j += 1
            jobs.append({"lines": cur, "cite": cite})
            cur = []
            i = j
            continue
        cur.append(ln)
        i += 1
    if cur:
        jobs.append({"lines": cur, "cite": None})
    return jobs


def drop_junk(lines):
    out, prev_head = [], False
    for ln in lines:
        t = ln["text"]
        if any(rx.search(t) for rx in JUNK):
            continue
        head = any(rx.search(t) for rx in HEAD_LINE)
        if head or (prev_head and HEAD_TAIL.match(t)):
            prev_head = True
            continue
        prev_head = False
        out.append(ln)
    return out


def split_apparatus(lines):
    """Отделить аппарат сносок от тела задания.

    Якорь — голое число мелким кеглем в левой колонке, за которым следует
    строка с отступом. Отступ обязателен: без него под правило попадает
    верхний индекс, оторвавшийся от своей строки в теле.
    """
    left, size = body_left(lines), body_size(lines)
    anchors = []
    for k, ln in enumerate(lines):
        # Вид первый: номер сноски вынесен отдельной строкой мелким кеглем,
        # текст сноски идёт следующей строкой с отступом.
        if NUM_ONLY.fullmatch(ln["text"]) and (ln.get("size") or 99) <= 9.0:
            nxt = lines[k + 1] if k + 1 < len(lines) else None
            if nxt is not None and nxt["x0"] >= ln["x0"] + 8 and (nxt.get("size") or 0) >= 9.5:
                anchors.append(k)
            continue
        # Вид второй: номер стоит ПЕРВЫМ словом строки, левее полосы набора,
        # и весь аппарат набран кеглем мельче тела. Так свёрстаны короткие
        # распечатки: у § 241 тело идёт с x0 96.4 кеглем 12.0, а аппарат — с
        # 70.2 кеглем 11.0. Без этого правила аппарат целиком остаётся в
        # тексте карточки, и сносок у неё не оказывается вовсе: у § 241 так
        # вышло 260 карточек и ни одной сноски.
        if left is None or size is None:
            continue
        if not HANG.match(ln["text"]):
            continue
        if ln["x0"] <= left - 8 and (ln.get("size") or 99) <= size - 0.5:
            anchors.append(k)
    if not anchors:
        return lines, []
    start = anchors[0]
    return lines[:start], lines[start:]


def unhang_notes(note_lines, left):
    """Развесить номера сносок, стоящие первым словом строки.

    `P.parse_notes` умеет два вида: «12. Текст» и голое число отдельной
    строкой. Третий вид — «12 Текст», где номер просто первое слово, — он не
    узнаёт, и весь аппарат уходит в одну безымянную сноску. Здесь такая
    строка разрезается на две: число и остаток. Признак — тот же висячий
    отступ, по которому аппарат и опознан.
    """
    if left is None:
        return note_lines
    out = []
    for ln in note_lines:
        m = HANG.match(ln["text"])
        if m and ln["x0"] <= left - 8:
            out.append(dict(ln, text=m.group(1)))
            out.append(dict(ln, text=m.group(2)))
        else:
            out.append(ln)
    return out


def body_left(lines):
    """Левый край полосы набора — по длинным строкам без висячего номера."""
    lefts = [ln["x0"] for ln in lines
             if len(ln["text"]) > 40 and not HANG.match(ln["text"])]
    return statistics.median(lefts) if len(lefts) >= 4 else None


def body_size(lines):
    """Кегль тела — по длинным строкам. Аппарат набран мельче."""
    sizes = [ln["size"] for ln in lines if len(ln["text"]) > 40 and ln.get("size")]
    return statistics.median(sizes) if len(sizes) >= 4 else None


def body_edge(lines):
    """Правый край полосы набора задания — по длинным нечисловым строкам."""
    rights = []
    for ln in lines:
        words = [w for w in ln["text"].split() if not NUM_ONLY.fullmatch(w)]
        if len(ln["text"]) > 40 and words:
            rights.append(ln["x1"])
    return statistics.median(rights) if len(rights) >= 4 else None


def pull_margin_numbers(lines):
    """Снять напечатанные Randnummern с концов строк.

    Номер стоит ПОСЛЕДНИМ словом строки и заходит за правый край полосы.
    Номер пишется прямо на строку полем `rn`, а сама строка чистится.

    Отдельный случай — номер, восстановленный распознаванием: ему не нашлось
    строки, и он пришёл строкой из одного числа. Он относится к СЛЕДУЮЩЕЙ
    строке тела, а сама строка-номер выбрасывается.
    """
    edge = body_edge(lines)
    if edge is None:
        return
    drop = []
    for k, ln in enumerate(lines):
        words = ln.get("words") or []
        if not words:
            continue
        if NUM_ONLY.fullmatch(ln["text"]) and ln["x0"] >= edge + 4:
            nxt = next((lines[j] for j in range(k + 1, len(lines))
                        if len(lines[j]["text"]) > 20), None)
            if nxt is not None and nxt.get("rn") is None:
                nxt["rn"] = int(ln["text"])
                drop.append(k)
            continue
        last = max(words, key=lambda w: w["x1"])
        tail = last["text"].strip()
        if NUM_ONLY.fullmatch(tail) and last["x0"] >= edge + 4 and len(ln["text"]) > 40:
            ln["rn"] = int(tail)
            keep = [w for w in words if w is not last]
            ln["words"] = keep
            ln["text"] = norm(" ".join(w["text"] for w in keep))
            ln["x1"] = max((w["x1"] for w in keep), default=ln["x1"])
    for k in sorted(drop, reverse=True):
        del lines[k]


def inline_superscripts(lines):
    """Вернуть оторвавшийся знак сноски в свою строку.

    Верхний индекс приподнят над строкой, и разбиение по высоте выносит его
    в отдельную строку из одного числа. Принадлежит он СЛЕДУЮЩЕЙ строке — там
    стоит слово, к которому относится, — и встаёт в неё на своё место по x.

    Делать это можно только ПОСЛЕ отделения аппарата: там номер сноски тоже
    стоит отдельной строкой из одного числа, и он там на своём месте.
    """
    res, pending = [], []
    for ln in lines:
        if NUM_ONLY.fullmatch(ln["text"]) and (ln.get("size") or 99) <= 9.0:
            pending.append(ln)
            continue
        if pending:
            words = sorted((ln.get("words") or []) + [w for m in pending for w in (m.get("words") or [])],
                           key=lambda w: w["x0"])
            ln = dict(ln, words=words, text=norm(" ".join(w["text"] for w in words)))
            pending = []
        res.append(ln)
    res.extend(pending)                     # знак в самом конце задания
    return res


def rn_list(s):
    """«9-12», «1, 3» → [9, 10, 11, 12], [1, 3]."""
    out = []
    for part in re.split(r",", s or ""):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if m and int(m.group(2)) >= int(m.group(1)):
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def job_units(job, warn):
    """Задание печати → список единиц (номер Rn, строки тела).

    Три случая, и различать их обязательно: напечатанные номера дают точную
    нарезку, одиночный номер в ссылке — тоже точную, а диапазон без
    напечатанных номеров даёт одну карточку на весь диапазон. Последнее —
    потеря дробности, и она считается.
    """
    clean = drop_junk(job["lines"])
    body, notes = split_apparatus(clean)
    notes = unhang_notes(notes, body_left(clean))
    cite = job["cite"]
    pull_margin_numbers(body)
    # Номер пишется НА строку, а не отдаётся списком индексов: вклейка знаков
    # сноски ниже меняет число строк, и любые индексы после неё врут.
    body = inline_superscripts(body)
    marks = [(k, ln["rn"]) for k, ln in enumerate(body) if ln.get("rn") is not None]
    want = rn_list(cite["rn"]) if cite and cite.get("rn") else []
    # Задание печати САМО говорит, какие Randnummern в нём напечатаны. Всё,
    # что распознано на поле вне этого списка, — не номер: это сбитая цифра
    # сноски или год из ссылки, попавший к правому краю. Без проверки такой
    # самозванец рвёт ряд на сотни номеров: у § 267 «199» вместо 25 давало
    # дыру в 174 номера, у § 305 «397» — в 273, у § 327c «281» — в 219.
    if want:
        allowed = set(want)
        marks = [(k, n) for k, n in marks if n in allowed]
        for k, ln in enumerate(body):
            if ln.get("rn") is not None and ln["rn"] not in allowed:
                warn["номер на поле вне задания"] += 1
                ln["rn"] = None

    if not body:
        return [], notes
    if marks:
        units = []
        # Текст до первого напечатанного номера принадлежит предыдущей
        # единице задания: она началась на прошлой полосе. Отдаём его первому
        # номеру диапазона, если он меньше первого напечатанного, иначе
        # приклеиваем к первой же единице.
        first_k, first_n = marks[0]
        head = body[:first_k]
        if head and want and want[0] < first_n:
            # Задание началось с номера, который на полосе не напечатан:
            # его абзац начался в предыдущем задании. Имя ему даёт ссылка.
            units.append({"number": want[0], "lines": head, "how": "ссылка"})
            head = []
        for j, (k, n) in enumerate(marks):
            end = marks[j + 1][0] if j + 1 < len(marks) else len(body)
            chunk = (head + body[k:end]) if j == 0 else body[k:end]
            head = []
            units.append({"number": n, "lines": chunk, "how": "поле"})
        return units, notes
    if want and len(want) == 1:
        return [{"number": want[0], "lines": body, "how": "ссылка"}], notes
    if want:
        warn["диапазон одной карточкой"] += 1
        return [{"number": want[0], "lines": body, "how": "диапазон", "upto": want[-1]}], notes
    warn["задание без номеров"] += 1
    return [{"number": 0, "lines": body, "how": "вступление"}], notes


def merge_units(units):
    """Склеить куски одной и той же Rn, попавшие в разные задания.

    Задания печати перекрываются: один и тот же номер печатается и в
    отдельном задании, и внутри диапазона. Берётся самый длинный вариант —
    короткий обычно обрывок, начатый на предыдущей полосе.
    """
    best = {}
    for u in units:
        key = (u["section"], u["number"], u.get("upto"))
        if key not in best or len(u["text"]) > len(best[key]["text"]):
            best[key] = u
    # Карточка на диапазон нужна лишь там, где номера поодиночке не нашлись.
    # Если каждый номер диапазона есть отдельной карточкой, диапазон — просто
    # обрывок того же текста, и держать его значит показывать одно место
    # дважды.
    single = {(u["section"], u["number"]) for u in best.values() if not u.get("upto")}
    out = [u for u in best.values()
           if not u.get("upto")
           or not all((u["section"], n) in single
                      for n in range(u["number"], u["upto"] + 1))]
    return sorted(out, key=lambda u: (u["par_sort"], u["number"]))


def par_sort_key(par):
    m = re.match(r"(\d+)([a-zä]*)", par)
    return (int(m.group(1)), m.group(2)) if m else (10 ** 6, par)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", help="диапазон страниц файла, напр. 1-200")
    ap.add_argument("--patches", help="work/patches.json от fill_outline_gaps.py")
    ap.add_argument("--jurisdiction", default="DE")
    ap.add_argument("--language", default="de")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = P.book_dirs(a.book)
    meta_path = os.path.join(a.book, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    book_id = meta.get("book_id") or os.path.basename(a.book.rstrip("/"))

    with pdfplumber.open(a.pdf) as pdf:
        idx = P.parse_range(a.pages, len(pdf.pages))
        print(f"полос в файле: {len(pdf.pages)}, разбирается: {len(idx)}", flush=True)
        patches = json.load(open(a.patches, encoding="utf-8")) if a.patches else {}
        if patches:
            print(f"возвращено контурных слов: {sum(len(v) for v in patches.values())}", flush=True)
        lines = read_lines(pdf, idx, patches)
    print(f"строк снято: {len(lines)}", flush=True)

    jobs = split_jobs(lines)
    print(f"заданий печати: {len(jobs)}", flush=True)

    warn = Counter()
    raw, texts = [], []
    offset = 0
    werk = None
    bearb = {}
    aufl = year = None
    for job in jobs:
        cite = job["cite"]
        if not cite:
            warn["задание без ссылки"] += 1
            continue
        par = ("Vor " if cite["vor"] else "") + cite["par"] + re.sub(r"\s+", " ", cite.get("qual") or "")
        werk = werk or cite["werk"]
        aufl = aufl or int(cite["aufl"])
        year = year or int(cite["year"])
        bearb.setdefault(par, cite["bearb"].strip())
        units, note_lines = job_units(job, warn)
        notes = P.parse_notes(note_lines, note_lines[0]["pdf_page"] if note_lines else 0)
        for n in notes:
            # В аппарате стрелка в конце записи — это кнопка «вернуться к
            # знаку» из веб-читалки, а не часть текста сноски. В текстовом
            # слое её нет, она приходит из распознавания контуров.
            n["text"] = re.sub(r"\s*→\s*$", "", n["text"]).strip()
        for u in units:
            text = join_hyphens("\n".join(ln["text"] for ln in u["lines"]).strip())
            if not text:
                continue
            u.update(section=par, par_sort=par_sort_key(cite["par"]), text=text,
                     notes=notes, page_start=u["lines"][0]["pdf_page"],
                     page_end=u["lines"][-1]["pdf_page"], gesetz=cite["gesetz"])
            raw.append(u)

    units = merge_units(raw)
    print(f"единиц после склейки: {len(units)}", flush=True)

    digest = P.sha256_file(a.pdf)
    cards = []
    for u in units:
        num = u["number"]
        rn = f"Rn. {num}" if not u.get("upto") else f"Rn. {num}-{u['upto']}"
        address = f"{u['gesetz']} § {u['section']} {rn}" if num else f"{u['gesetz']} § {u['section']} Schrifttum und Übersicht"
        who = bearb.get(u["section"], "")
        citation = f"{werk}/{who}, {aufl}. Aufl. {year}, {address}"
        ext = f"{book_id}:rn:{u['section']}/{num}" + (f"-{u['upto']}" if u.get("upto") else "")
        # Сноска привязывается по знаку в тексте карточки, а не по полосе:
        # аппарат стоит в конце задания и полосой с текстом не совпадает.
        mine = [n for n in u["notes"] if n.get("number") is not None
                and re.search(r"(?<!\d)%d(?!\d)" % n["number"], u["text"])]
        start = offset
        texts.append(u["text"])
        offset += len(u["text"]) + 1
        cards.append({
            "external_id": ext,
            "id": f"{book_id}-rn{u['section']}-{num}",
            "book_id": book_id,
            "unit": "Rn.", "unit_type": "Rn.", "unit_number": str(num), "number": num,
            "section": u["section"],
            "address": address,
            "citation": citation,
            "text": u["text"],
            "hierarchy": [f"§ {u['section']}"],
            "footnotes": sorted(mine, key=lambda n: n["number"]),
            "statutory_refs": [], "cross_refs": [],
            # Задание печати на диапазон без напечатанных номеров даёт одну
            # карточку; номера, оставшиеся внутри неё, перечисляются здесь,
            # иначе они выглядят просто потерянными.
            "contains_also": [
                {"external_id": f"{book_id}:rn:{u['section']}/{n}", "unit_type": "Rn.",
                 "number": n, "reason": "номер не напечатан в распечатке"}
                for n in range(num + 1, (u.get("upto") or num) + 1)],
            "institute": None, "concept_ids": [],
            "source": {k: meta.get(k) for k in ("authors", "title", "edition", "year", "publisher")},
            "jurisdiction": meta.get("jurisdiction") or a.jurisdiction,
            "language": meta.get("language") or a.language,
            "page_start": u["page_start"], "page_end": u["page_end"],
            "printed_page_start": None, "printed_page_end": None,
            "char_start": start, "char_end": offset - 1,
            "bbox": [],
            "source_file": os.path.basename(a.pdf),
            "source_sha256": digest,
            "method": "digital",
            "detection_mode": u["how"],
            "detection_evidence": {"job": u["how"]},
            "profile": "beck-online-print-v1",
            "chunk_version": P.SCHEMA_VERSION,
        })

    print(f"карточек: {len(cards)}; со сносками: {sum(1 for c in cards if c['footnotes'])}")
    how = Counter(c["detection_mode"] for c in cards)
    print("  откуда номер:", ", ".join(f"{k} {v}" for k, v in how.most_common()))
    for k, v in warn.most_common():
        print(f"  ВНИМАНИЕ: {k}: {v}")
    if a.dry_run:
        return
    P.atomic_write(os.path.join(d["work"], "book.txt"), "\n".join(texts))
    P.write_json(os.path.join(d["work"], "pages_meta.json"), {
        "source_pdf": os.path.abspath(a.pdf), "source_sha256": digest,
        "branch": "beck", "method": "digital", "profile": "beck-online-print-v1",
        "pages_requested": len(idx), "pages_built": len(idx), "pages_empty": 0,
        "schema_version": P.SCHEMA_VERSION,
    })
    P.write_jsonl(os.path.join(d["output"], "cards.jsonl"), cards)
    print(f"Записано: {d['output']}/cards.jsonl")


if __name__ == "__main__":
    main()
