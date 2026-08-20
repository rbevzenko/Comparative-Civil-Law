#!/usr/bin/env python3
"""
Общие примитивы пайплайна: атомарная запись, хеши, модель страницы,
сборка строк из символов или OCR-слов, отделение сносок, колонцифры.

Модуль не принимает предметных решений. Всё, что зависит от книги,
приходит из профиля; всё, что нельзя получить механически, поднимается
наверх как запись в issues, а не додумывается.

Модель страницы — общий шов двух веток. Ветка A (pages_digital.py) и
ветка B (ocr.py) пишут один и тот же формат work/pages.jsonl, но остаются
разными скриптами: у них разные режимы отказа, и сливать их нельзя.

    {
      "pdf_page": 1,              # индекс страницы в файле, с единицы
      "printed_page": 23,         # типографская колонцифра, либо null
      "width": 595.0, "height": 842.0,
      "method": "digital" | "ocr:<engine>",
      "lines": [ {...} ],         # тело полосы
      "note_lines": [ {...} ]     # блок сносок
    }

Строка:

    {"text": "...", "x0":.., "x1":.., "top":.., "bottom":.., "size":..}
    плюс "words": [{"text","x0","x1","top","bottom"}] — нужны маргинальному режиму
"""

import hashlib
import json
import os
import re
import statistics
import tempfile
import unicodedata

SCHEMA_VERSION = 2


# ---------- запись без риска потерять уже сделанное ----------

def atomic_write(path, data, binary=False):
    """Запись через временный файл в том же каталоге + rename.

    Длинная книга обрабатывается часами; обрыв на середине записи не должен
    оставлять полуфайл, по которому следующий запуск решит, что страница готова.
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    mode = "wb" if binary else "w"
    kw = {} if binary else {"encoding": "utf-8"}
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    os.close(fd)
    try:
        with open(tmp, mode, **kw) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2))


def write_jsonl(path, rows):
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_range(spec, n_pages):
    """'40-1200' → индексы страниц с нуля. Пусто → вся книга."""
    if not spec:
        return list(range(n_pages))
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo) - 1, min(n_pages, int(hi or lo))))
    return sorted(set(out))


def book_dirs(root):
    """Каталог книги по §17 спецификации."""
    d = {k: os.path.join(root, k) for k in ("source", "cache", "ocr", "work", "output", "report")}
    for p in d.values():
        os.makedirs(p, exist_ok=True)
    return d


# ---------- сборка строк ----------

def cluster_lines(tokens, tol=None):
    """Токены (символы или слова) → строки.

    Строка собирается по вертикальному центру и с оглядкой на кегль, а не по
    округлённой координате top. Причина не теоретическая: сноска мелким кеглем
    и последняя строка тела стоят на полосе почти на одной высоте, и наивная
    кластеризация сплетает их посимвольно в одну строку-кашу. Так же ведут
    себя маргиналия рядом с телом и колонтитул над первой строкой.
    """
    if not tokens:
        return []
    rows = []
    for t in sorted(tokens, key=lambda t: (t["top"], t["x0"])):
        h = max(1.0, t["bottom"] - t["top"])
        c = (t["top"] + t["bottom"]) / 2
        size = t.get("size") or h
        placed = False
        for row in reversed(rows[-3:]):                # строки идут сверху вниз
            rh = max(1.0, row["bottom"] - row["top"])
            rc = (row["top"] + row["bottom"]) / 2
            rsize = row["size"] or rh
            near = abs(c - rc) <= (tol if tol is not None else 0.45 * max(h, rh))
            same_size = max(size, rsize) / max(0.1, min(size, rsize)) <= 1.6
            # Верхний индекс — знак сноски, номер на поле, мелкая цифра перед
            # текстом — кегль имеют другой, но принадлежат этой же строке.
            # Признак — вертикальная вложенность плюс соседство сбоку, а не
            # наложение: наложение как раз означает две разные строки.
            inside = t["top"] >= row["top"] - 0.35 * rh and t["bottom"] <= row["bottom"] + 0.35 * rh
            rx0 = min(i["x0"] for i in row["items"])
            rx1 = max(i["x1"] for i in row["items"])
            beside = t["x0"] >= rx1 - 1.0 or t["x1"] <= rx0 + 1.0
            gap = min(abs(t["x0"] - rx1), abs(rx0 - t["x1"]))
            if near and (same_size or (inside and beside and gap <= 3 * rh)):
                row["items"].append(t)
                row["top"] = min(row["top"], t["top"])
                row["bottom"] = max(row["bottom"], t["bottom"])
                placed = True
                break
        if not placed:
            rows.append({"items": [t], "top": t["top"], "bottom": t["bottom"], "size": size})
    rows.sort(key=lambda r: (r["top"], min(i["x0"] for i in r["items"])))
    return [r["items"] for r in rows]


def drop_phantom_spaces(row):
    """Убирает пробельные глифы, нарисованные поверх соседней буквы.

    У Pearson (Smith, Property Law: Cases and Materials, 6th ed.) шрифт
    ставит лишние пробелы поверх глифов, и текстовый слой рвёт слова:
    «Th e», «signifi cance», «aft er», «Y axley», «L and Law». Разрывов на
    книгу около 850.

    Разбираются два случая, и оба — в порядке ПОТОКА, а не по x0:
    сортировка по x0 сама по себе перемешивает пробел с курсивным глифом,
    который начинается на сотую долю пункта левее.

    1. Пробел нарисован ПОВЕРХ предыдущего глифа: у лигатуры «Th»
       (104.88–115.59) следом идёт пробел 110.23–112.50, целиком внутри
       буквы. Такой пробел ненастоящий.
    2. Из пары одинаковых пробелов между курсивом и прямым начертанием
       («Ingram  v  IRC») второй налезает на следующий глиф. Первый —
       настоящий, второй лишний; условие «перед ним тоже пробел» и
       отличает эту пару от одиночного настоящего пробела.

    Настоящий одиночный пробел стоит между глифами и ни на один не
    налезает, поэтому книгам без этого дефекта правило ничего не делает.
    """
    if any("_stream" in c for c in row):
        order = sorted(row, key=lambda c: c["_stream"])
    else:
        order = sorted(row, key=lambda c: c["x0"])
    drop = set()
    n = len(order)
    for i, ch in enumerate(order):
        if not (ch.get("text") or "").isspace():
            continue
        w = max(ch["x1"] - ch["x0"], 0.01)
        prev = order[i - 1] if i else None
        nxt = order[i + 1] if i + 1 < n else None
        prev_is_space = prev is None or (prev.get("text") or "").isspace()
        if prev is not None and not prev_is_space:
            ov = min(ch["x1"], prev["x1"]) - max(ch["x0"], prev["x0"])
            if ov > 0.5 * w:
                drop.add(id(ch))
                continue
        if prev_is_space and nxt is not None and not (nxt.get("text") or "").isspace():
            ov = min(ch["x1"], nxt["x1"]) - max(ch["x0"], nxt["x0"])
            if ov > 0.25 * w:
                drop.add(id(ch))

    # Второй проход — уже в порядке x0, в котором строка и будет собрана.
    # Сортировка ставит пробел то до, то после налезающего на него глифа
    # (ключ у cluster_lines — (top, x0), а top у пробела и у буквы разные),
    # поэтому одного прохода по потоку мало: «( 2) H ow» получается из
    # пробелов, уехавших ЗА свою букву. Здесь условие строже — пробел должен
    # целиком помещаться внутри соседнего глифа; настоящий пробел стоит
    # встык и внутрь не помещается никогда.
    rest = [c for c in row if id(c) not in drop]
    rest.sort(key=lambda c: c["x0"])
    for i, ch in enumerate(rest):
        if not (ch.get("text") or "").isspace():
            continue
        # Соседа ищем через пробелы: подряд идущих пробелов бывает по три,
        # и «ближайший сосед по списку» у второго из них — снова пробел.
        left = next((o for o in reversed(rest[:i]) if not (o.get("text") or "").isspace()), None)
        right = next((o for o in rest[i + 1:] if not (o.get("text") or "").isspace()), None)
        for o in (left, right):
            if o is None:
                continue
            if ch["x0"] >= o["x0"] - 0.05 and ch["x1"] <= o["x1"] + 0.05:
                drop.add(id(ch))
                break
    return [c for c in row if id(c) not in drop]


def case_width_table(chars, table=None):
    """Копит ширины строчных букв по шрифтам: (fontname, буква) → {ширины}."""
    table = table if table is not None else {}
    for c in chars:
        t = c.get("text") or ""
        if len(t) != 1 or not t.isalpha() or not t.islower():
            continue
        size = c.get("size") or 0
        if size <= 0:
            continue
        table.setdefault((c.get("fontname"), t), set()).add(round((c["x1"] - c["x0"]) / size, 3))
    return table


def case_upper_widths(table):
    """Из таблицы ширин — ширина ПРОПИСНОЙ для каждой испорченной буквы."""
    upper = {}
    for key, ws in table.items():
        lo, hi = min(ws), max(ws)
        # Порог 1.04 отделяет пару «строчная/прописная» от дрожания
        # округления: у «m» и «M» разница всего 7% (0.778 против 0.833).
        if len(ws) >= 2 and hi >= lo * 1.04:
            upper[key] = hi
    return upper


def repair_case_by_width(chars, upper=None):
    """Возвращает регистр буквам, у которых во встроенном шрифте перепутан ToUnicode.

    У Pearson (Duddington, Law Express: Land Law, 3rd ed.) часть глифов
    отдаёт в текстовый слой строчную букву вместо прописной: «lAnd lAw»
    вместо «LAND LAW», «the law of Property act 1925» вместо «the Law of
    Property Act 1925», «EWCa Civ 347», «ukHL 17».

    Высота глифа тут не помогает — pdfplumber отдаёт её равной кеглю, — а
    ШИРИНА помогает: в Helvetica прописная и строчная одной буквы всегда
    разной ширины. В шрифте страницы у испорченной буквы ровно два значения
    ширины: настоящее строчное («l» — 0.222 кегля) и прописное («L» — 0.5).
    Большее и есть прописная.

    Таблица ширин собирается по ВСЕЙ книге и передаётся сюда готовой: буква,
    встречающаяся на одной полосе только в испорченном виде («k» в «kEy
    CASE»), по этой полосе неотличима, а по книге — отличима.
    """
    def norm(c):
        size = c.get("size") or 0
        if size <= 0:
            return None
        return round((c["x1"] - c["x0"]) / size, 3)

    if upper is None:
        upper = case_upper_widths(case_width_table(chars))

    if not upper:
        return chars
    for c in chars:
        t = c.get("text") or ""
        if len(t) != 1 or not t.isalpha() or not t.islower():
            continue
        target = upper.get((c.get("fontname"), t))
        if target is None:
            continue
        w = norm(c)
        if w is not None and abs(w - target) < 0.006:
            c["text"] = t.upper()
    return chars


def chars_to_lines(chars):
    """Ветка A: символы pdfplumber → строки со словами и координатами."""
    for i, ch in enumerate(chars):
        if "_stream" not in ch:
            ch["_stream"] = i
    lines = []
    for row in cluster_lines(chars):
        row = drop_phantom_spaces(sorted(row, key=lambda c: c["x0"]))
        if not row:
            continue
        words, buf, prev = [], [], None
        gap = _space_gap(row)
        for ch in row:
            if prev is not None and ch["x0"] - prev > gap:
                if buf:
                    words.append(_mk_word(buf))
                buf = []
            buf.append(ch)
            prev = ch["x1"]
        if buf:
            words.append(_mk_word(buf))
        if not words:
            continue
        lines.append(_mk_line(words, size=_median([c["size"] for c in row])))
    return lines


def words_to_lines(words, group_key=None):
    """Ветка B: слова OCR → строки.

    Если движок сам сообщил, какие слова в одной строке (group_key), берём его
    разбиение: оно опирается на изображение, а наша кластеризация — только на
    рамки, и на разорванных словах ошибается, вынося обрывок в отдельную
    строку и ломая порядок чтения.
    """
    if group_key:
        groups = {}
        for w in words:
            groups.setdefault(w.get(group_key), []).append(w)
        rows = list(groups.values())
    else:
        rows = cluster_lines(words)
    lines = []
    for row in rows:
        row = sorted(row, key=lambda w: w["x0"])
        lines.append(_mk_line(row, size=_median([w.get("size", 0) for w in row]) or None))
    lines = [l for l in lines if l["text"]]
    lines.sort(key=lambda l: (round(l["top"], 1), l["x0"]))
    return lines


def _space_gap(row):
    """Порог пробела: доля от типичной ширины символа строки."""
    widths = [c["x1"] - c["x0"] for c in row if c["x1"] > c["x0"]]
    return max(0.8, (statistics.median(widths) if widths else 4.0) * 0.35)


def _mk_word(chs):
    return {
        # Подряд идущие пробелы схлопываются: у книг с двойным пробелом между
        # курсивом и прямым начертанием («Ingram  v  IRC») иначе остаётся
        # рваная разрядка внутри названия дела.
        "text": re.sub(r"\s{2,}", " ", "".join(c["text"] for c in chs)).strip(),
        "x0": min(c["x0"] for c in chs), "x1": max(c["x1"] for c in chs),
        "top": min(c["top"] for c in chs), "bottom": max(c["bottom"] for c in chs),
        "size": _median([c["size"] for c in chs]),
    }


def _mk_line(words, size=None):
    words = [w for w in words if w["text"]]
    return {
        "text": " ".join(w["text"] for w in words).strip(),
        "x0": min((w["x0"] for w in words), default=0.0),
        "x1": max((w["x1"] for w in words), default=0.0),
        "top": min((w["top"] for w in words), default=0.0),
        "bottom": max((w["bottom"] for w in words), default=0.0),
        "size": size,
        "words": words,
    }


def _median(xs):
    xs = [x for x in xs if x]
    return round(statistics.median(xs), 2) if xs else None


def body_bands(pages):
    """Границы колонки тела отдельно для чётных и нечётных страниц.

    У книг с зеркальными полями (а это норма для немецких комментариев)
    колонка тела сдвинута на развороте, и общая на книгу граница не годится:
    маргиналия recto оказывается внутри «тела» verso и наоборот.
    """
    from collections import Counter
    out = {}
    for name, want_odd in (("odd", True), ("even", False)):
        x0 = Counter(); x1 = Counter()
        for pg in pages:
            if (pg["pdf_page"] % 2 == 1) != want_odd:
                continue
            for ln in pg["lines"]:
                if len(ln["text"]) > 40:
                    x0[round(ln["x0"])] += 1
                    x1[round(ln["x1"])] += 1
        out[name] = (float(x0.most_common(1)[0][0]) if x0 else None,
                     float(x1.most_common(1)[0][0]) if x1 else None)
    if out["odd"][0] is None:
        out["odd"] = out["even"]
    if out["even"][0] is None:
        out["even"] = out["odd"]
    return out


def band_for(page_no, bands):
    return bands["odd" if page_no % 2 == 1 else "even"]


def margin_columns(pages, bin_pt=6.0, min_hits=5, side=None, parity=None):
    """Колонки маргинальных номеров по вертикальной массе текста.

    Считать поле «всё, что левее края тела» нельзя: край тела сам считается
    по строкам, а строка с маргиналией на ту же величину и длиннее. Полоса
    тогда уезжает на саму маргиналию и режим перестаёт работать ровно на тех
    книгах, ради которых он написан.

    Поэтому колонка ищется как вертикальный коридор, где почти нет буквенного
    текста, но регулярно стоят одинокие числа. Это и есть типографская улика,
    а не одна координата x (§7, режим 2).
    """
    from collections import Counter, defaultdict
    out = {}
    for name, want_odd in (("odd", True), ("even", False)):
        alpha = defaultdict(Counter)          # страница → корзина → масса букв
        nums = defaultdict(list)              # корзина → страницы с одиноким числом
        page_w = 0.0
        for pg in pages:
            # Сторона разворота определяется типографской страницей, а не
            # индексом в файле: при препринте в 35 страниц recto книги
            # приходится на чётную страницу файла, и поля «переворачиваются».
            pno = (pg.get("printed_page") or pg["pdf_page"]) if parity == "printed" else pg["pdf_page"]
            if (pno % 2 == 1) != want_odd:
                continue
            page_w = max(page_w, pg.get("width") or 0.0)
            for ln in pg["lines"]:
                for w in ln.get("words", []):
                    s = w["text"].strip()
                    b = int(((w["x0"] + w["x1"]) / 2) // bin_pt)
                    if re.fullmatch(r"\d{1,4}", s):
                        nums[b].append(pg["pdf_page"])
                    elif sum(ch.isalpha() for ch in s) >= 3:
                        for bb in range(int(w["x0"] // bin_pt), int(w["x1"] // bin_pt) + 1):
                            alpha[pg["pdf_page"]][bb] += len(s)
        if not nums:
            out[name] = []
            continue

        # Граница текстовой полосы считается по СЛОВАМ, а не по строкам, и
        # только по нечисловым: строка, начинающаяся с маргинального номера
        # или кончающаяся числом внутри текста, иначе растягивает полосу на
        # само поле, и коридор перестаёт быть коридором.
        left_edges, right_edges = [], []
        for pg in pages:
            pno = (pg.get("printed_page") or pg["pdf_page"]) if parity == "printed" else pg["pdf_page"]
            if (pno % 2 == 1) != want_odd:
                continue
            for ln in pg["lines"]:
                words = [w for w in ln.get("words", [])
                         if not re.fullmatch(r"\d{1,4}", w["text"].strip())]
                if len(ln["text"]) > 40 and words:
                    left_edges.append(min(w["x0"] for w in words))
                    right_edges.append(max(w["x1"] for w in words))
        body_l = statistics.median(left_edges) if left_edges else None
        body_r = statistics.median(right_edges) if right_edges else None

        # Коридор проверяется на тех страницах, где он используется, а не по
        # книге целиком: у задачника в конце тома своя вёрстка, и общая на
        # книгу статистика затопила бы поле основного текста чужой массой.
        quiet = set()
        for b, pgs in nums.items():
            pgs = sorted(set(pgs))
            if len(pgs) < 3:
                continue
            here = statistics.mean(alpha[p].get(b, 0) for p in pgs)
            widest = statistics.mean(max(alpha[p].values(), default=0) for p in pgs)
            if widest and here < 0.05 * widest:
                quiet.add(b)

        cols, cur = [], []
        for b in sorted(quiet):
            if cur and b - cur[-1] <= 1:
                cur.append(b)
            else:
                if cur:
                    cols.append(cur)
                cur = [b]
        if cur:
            cols.append(cur)

        found = []
        for c in cols:
            hits = sum(len(nums[b]) for b in c)
            if hits < min_hits:
                continue
            # Полкорзины запаса с каждой стороны: номер на поле шириной в две
            # цифры попадает центром ровно на границу корзины, и без запаса
            # часть номеров (а с ними и единиц книги) выпадает из коридора.
            x0 = max(0.0, min(c) * bin_pt - bin_pt * 0.5)
            x1 = (max(c) + 1) * bin_pt + bin_pt * 0.5
            where = "left" if (x0 + x1) / 2 < page_w / 2 else "right"
            # Поле — это то, что ЗА полосой набора. Числа в конце строки или
            # в сноске стоят внутри полосы и маргиналиями не являются.
            pad = 6.0
            if where == "left" and body_l is not None:
                x1 = min(x1, body_l - pad)
            if where == "right" and body_r is not None:
                x0 = max(x0, body_r + pad)
            if x1 - x0 < bin_pt * 0.5:
                continue
            if side and side != "both" and where != side:
                continue
            found.append({"x0": x0, "x1": x1, "hits": hits, "side": where})
        out[name] = sorted(found, key=lambda f: -f["hits"])
    return out


def margin_side(page_no, cfg):
    """Сторона поля с учётом разворота: outer/inner меняются на каждой странице."""
    side = cfg.get("side", "left")
    if side in ("left", "right", "both"):
        return side
    recto = page_no % 2 == 1
    if side == "outer":
        return "right" if recto else "left"
    if side == "inner":
        return "left" if recto else "right"
    return "left"


# ---------- мусор, колонцифры, сноски ----------

ROMAN = re.compile(r"^[ivxlcdm]{1,8}$", re.IGNORECASE)


def detect_printed_page(lines, height, band=0.12, patterns=None):
    """Совместимость: только номер, без строки, в которой он найден."""
    return detect_printed_page_line(lines, height, band, patterns)[0]


def detect_printed_page_line(lines, height, band=0.12, patterns=None, max_chars=70):
    """Типографская колонцифра из верхней или нижней полосы.

    Спецификация §10: номер страницы файла не равен номеру страницы книги,
    и второй нужно прочитать со страницы, а не вычислить смещением.

    Колонцифра не всегда стоит отдельной строкой: у книг с колонтитулом она
    сидит внутри него («18 Das Recht im objektiven Sinn» на чётной, «… 19»
    на нечётной). Такие случаи описываются паттернами в профиле.
    """
    # `band` — либо одно число (обе полосы одинаковы), либо пара
    # [верхняя, нижняя]. Пара нужна там, где колонтитул стоит ниже, чем
    # колонцифра снизу: у Duddington колонтитул на 0.075 высоты, а
    # колонцифра — на 0.93, и симметричная полоса ловит либо оба, либо
    # ничего. Из колонтитула «10 Adverse possession» при этом приезжает
    # номер главы вместо номера страницы.
    if isinstance(band, (list, tuple)):
        top_frac, bottom_frac = float(band[0]), float(band[1])
    else:
        top_frac = bottom_frac = float(band)
    top_band, bottom_band = height * top_frac, height * (1 - bottom_frac)
    rx = [re.compile(p) for p in (patterns or [])]
    for i, ln in enumerate(lines):
        s = ln["text"].strip()
        if ln["top"] > top_band and ln["bottom"] < bottom_band:
            continue
        m = re.fullmatch(r"[\[\(]?(\d{1,4})[\]\)]?", s)
        if m:
            return int(m.group(1)), i
        if ROMAN.fullmatch(s):
            return None, i         # римская пагинация: препринт, не тело книги
        # Колонтитул короткий. Ограничение по длине обязательно: на странице
        # без колонтитула паттерн «номер в начале строки» иначе цепляется за
        # первую строку текста, и маргинальный номер этой единицы уходит в
        # колонцифру, а сама строка снимается как колонтитул.
        if len(s) <= max_chars:
            for r in rx:
                m = r.search(s)
                if m:
                    try:
                        return int(m.group(1)), i
                    except (IndexError, ValueError):
                        continue
    return None, None


def strip_bands(lines, height, header=None, footer=None):
    """Снимает колонтитул и нижнюю плашку по полосам страницы.

    Колонтитул выбрасывается ПОСЛЕ чтения колонцифры: у многих книг номер
    страницы живёт именно в нём, и порядок здесь не косметический.
    """
    if not height or (header is None and footer is None):
        return lines
    hi = height * header if header else None
    lo = height * footer if footer else None
    out = []
    for ln in lines:
        if hi is not None and ln["bottom"] <= hi:
            continue
        if lo is not None and ln["top"] >= lo:
            continue
        out.append(ln)
    return out


def strip_junk(lines, junk_rx, printed_page, height=None, band=0.12):
    """Снимает водяные знаки, колонтитулы и одинокую колонцифру.

    Одинокое число выбрасывается только из верхней и нижней полосы. В теле
    полосы одинокое число — это маргинальный номер, то есть ровно то, ради
    чего всё делается; книга с Randziffern иначе теряет все свои адреса.

    И даже в полосе выбрасывается не всякое число, а только то, которое
    СОВПАЛО с колонцифрой этой страницы. Маргинальный номер тоже иногда
    заходит в полосу — у Praxiskommentar GmbHG (Verlag Österreich 2017) Rz3
    к §91 стоит на 0.105 высоты, отдельной строкой, и слепое правило съедало
    его вместе с карточкой. Колонцифра здесь известна: её нашли строкой выше,
    и сверить с ней дешевле, чем терять единицу.
    """
    out = []
    for ln in lines:
        s = ln["text"].strip()
        if not s:
            continue
        in_margin_band = height is None or ln["top"] < height * band or ln["bottom"] > height * (1 - band)
        m = re.fullmatch(r"[\[\(]?(\d{1,4})[\]\)]?", s)
        if m and in_margin_band and (printed_page is None or int(m.group(1)) == printed_page):
            continue
        if any(rx.search(s) for rx in junk_rx):
            continue
        out.append(ln)
    return out


def split_footnotes(lines, height, prof, method):
    """Отделение блока сносок от тела полосы.

    Ветка A: кегль плюс положение. Ветка B: только положение —
    кегль в OCR ненадёжен (§9 спецификации).
    """
    fn = prof.get("footnotes", {}) or {}
    mode = fn.get("mode", "font_bottom")
    band = float(fn.get("bottom_band", 0.70))
    if mode == "none" or not lines:
        return lines, []

    cutoff_y = height * band
    note_max = fn.get("note_size_max")
    if note_max is None and not method.startswith("ocr"):
        sizes = [l["size"] for l in lines if l["size"]]
        note_max = (statistics.median(sizes) - 1.5) if sizes else None

    if method.startswith("ocr") or mode == "position_bottom" or note_max is None:
        # Ветка B: блок сносок — хвост полосы. Якорь по знаку сноски работает
        # только там, где знак распознан: верхний индекс OCR регулярно
        # превращает в мусор («®)», «Ss!)», «>)»), и строгий якорь тогда
        # теряет весь блок. Поэтому вторым признаком берётся рост кегля:
        # хвост страницы, набранный мельче основного текста, и есть сноски.
        for rule in (_first_note_line_by_position, _gap_tail, _small_type_tail):
            start = rule(lines, cutoff_y)
            if start is not None and _tail_looks_like_notes(lines, start, note_max):
                return lines[:start], lines[start:]
        return lines, []

    # Ветка A: решение принимается по каждой строке отдельно, а не одной
    # границей. Последний абзац единицы нередко заходит в зону сносок, и
    # хвостовое правило утащило бы его в сноски целиком.
    body, notes = [], []
    for ln in lines:
        is_note = ln["top"] >= cutoff_y and ln["size"] is not None and ln["size"] <= note_max
        (notes if is_note else body).append(ln)
    return body, notes


def _tail_looks_like_notes(lines, start, note_max=None):
    """Проверка найденного хвоста: сноски он или всё-таки текст.

    Отбивка перед подзаголовком шире интерлиньяжа так же, как отбивка перед
    сносками. Без проверки конец полосы вместе с заголовком и началом
    следующей единицы уезжает в сноски, а книга теряет её номер.

    Проверок две, и хватает любой:
      * кегль — там, где он о чём-то говорит. У чужого OCR-слоя он бывает
        синтетическим: всем строкам, включая сноски, проставлено одно
        значение, и сравнивать нечего;
      * знак сноски в начале хвоста. Знак числовой, пусть и попорченный
        распознаванием («I4)», «,2)»); буквенная рубрика («C. Schuldbegrenzung»)
        под это не подходит и хвостом сносок не считается.
    """
    tail, body = lines[start:], lines[:start]
    if not tail:
        return False

    tail_sizes = [l["size"] for l in tail if l.get("size")]
    body_sizes = [l["size"] for l in body if l.get("size")]
    if note_max is not None and tail_sizes:
        if statistics.median(tail_sizes) <= note_max + 0.3:
            return True
    if len(body_sizes) >= 3 and tail_sizes:
        if statistics.median(tail_sizes) <= statistics.median(body_sizes) - 0.8:
            return True

    numeric_marker = re.compile(r"^\S{0,2}\d{1,3}\s*[\)\.]\s")
    return any(NOTE_START.match(l["text"]) or numeric_marker.match(l["text"]) for l in tail[:2])


def _first_note_line_by_position(lines, cutoff_y):
    """Первая строка в нижней полосе, начинающаяся с номера сноски."""
    for i, ln in enumerate(lines):
        if ln["top"] >= cutoff_y and NOTE_START.match(ln["text"]):
            return i
    return None


def _gap_tail(lines, cutoff_y, factor=1.7):
    """Начало блока сносок по разрыву между строками.

    Над сносками стоит отбивка (у многих книг ещё и линейка), и она шире
    обычного интерлиньяжа в полтора-два раза. Это чисто позиционный признак,
    как и требует §9: в OCR он переживает то, чего не переживает кегль, —
    верхний индекс знака сноски регулярно распознаётся мусором.
    """
    tops = sorted(l["top"] for l in lines)
    steps = [b - a for a, b in zip(tops, tops[1:]) if b > a]
    if len(steps) < 5:
        return None
    lead = statistics.median(steps)
    ordered = sorted(range(len(lines)), key=lambda i: lines[i]["top"])
    for k, i in enumerate(ordered[1:], start=1):
        ln = lines[i]
        prev = lines[ordered[k - 1]]
        if ln["top"] < cutoff_y:
            continue
        if ln["top"] - prev["top"] >= lead * factor and len(lines) - k >= 2:
            return i
    return None


def _line_height(ln):
    return max(1.0, ln["bottom"] - ln["top"])


def _small_type_tail(lines, cutoff_y, ratio=0.88, min_lines=2):
    """Начало хвоста страницы, целиком набранного мельче основного текста.

    Признак не про кегль как таковой (в OCR он ненадёжен), а про перелом:
    от какой-то строки и до низа полосы все строки ниже ростом. Так выглядит
    блок сносок и не выглядит обычный абзац.
    """
    body = [_line_height(l) for l in lines if l["top"] < cutoff_y]
    if len(body) < 3:
        return None
    base = statistics.median(body)
    for i, ln in enumerate(lines):
        if ln["top"] < cutoff_y:
            continue
        tail = lines[i:]
        if len(tail) < min_lines:
            return None
        if all(_line_height(t) <= base * ratio for t in tail):
            return i
    return None


# Знак сноски: номер ОБЯЗАТЕЛЬНО со скобкой или точкой. Без этого условия
# правило принимает за сноску маргинальный номер, приклеившийся к первой
# строке абзаца («220 Aufhebung der Verbindlichkeit…»), и конец полосы вместе
# с единицей уезжает в сноски.
NOTE_START = re.compile(r"^(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[\).])\s+(?=\S)")


def parse_notes(note_lines, page):
    """Блок сносок → список {number, text, page}.

    Номер сноски локален для страницы, поэтому page обязателен.
    """
    notes, cur, pending = [], None, None
    for ln in note_lines:
        s = ln["text"].strip()
        if not s:
            continue
        # Знак сноски набран верхним индексом и мог не склеиться со своей
        # строкой. Тогда он приходит отдельной строкой из одного числа, и
        # текстом сноски служит следующая строка.
        m_only = re.fullmatch(r"[\(\[]?(\d{1,3})[\)\].]?", s)
        if m_only:
            if cur:
                notes.append(cur)
                cur = None
            pending = int(m_only.group(1))
            continue
        m = NOTE_START.match(s)
        if m:
            if cur:
                notes.append(cur)
            num = next(g for g in m.groups() if g)
            cur = {"number": int(num), "text": s[m.end():].strip(), "page": page}
            pending = None
        elif pending is not None:
            if cur:
                notes.append(cur)
            cur = {"number": pending, "text": s, "page": page}
            pending = None
        elif cur:
            cur["text"] += " " + s
    if cur:
        notes.append(cur)
    if not notes and note_lines:
        # Блок сносок найден, но ни один знак не прочитался: в сканах верхний
        # индекс регулярно превращается в мусор. Текст сохраняем целиком с
        # номером None — потерять его молча хуже, чем показать неразобранным.
        notes.append({"number": None, "page": page, "unparsed": True,
                      "text": " ".join(l["text"].strip() for l in note_lines).strip()})
    return notes


# ---------- последовательность номеров и OCR-подмены ----------

OCR_SUBST = {
    "0": "OoDQ", "1": "lIi|", "2": "Zz", "3": "8B", "4": "A",
    "5": "SsG", "6": "Gb", "7": "T", "8": "3BS", "9": "gq",
}
OCR_BACK = {}
for _d, _chars in OCR_SUBST.items():
    for _c in _chars:
        OCR_BACK.setdefault(_c, set()).add(_d)


def repair_number(raw, expected):
    """Проверка номера по ожидаемому следующему с учётом подмен OCR.

    Возвращает (номер, запись аудита) либо (None, запись), если починить
    нечем. Молча номер не меняется никогда: §8 требует следа.
    """
    if raw.isdigit():
        return int(raw), None
    variants = {""}
    for ch in raw:
        nxt = set()
        for v in variants:
            if ch.isdigit():
                nxt.add(v + ch)
            for d in OCR_BACK.get(ch, ()):
                nxt.add(v + d)
        variants = nxt or {""}
        if len(variants) > 64:
            break
    cands = sorted({int(v) for v in variants if v.isdigit()})
    if not cands:
        return None, {"raw": raw, "action": "unreadable", "expected": expected}
    if expected is not None and expected in cands:
        return expected, {"raw": raw, "action": "repaired", "to": expected,
                          "expected": expected, "candidates": cands[:8]}
    return cands[0], {"raw": raw, "action": "guessed_first_candidate",
                      "to": cands[0], "expected": expected, "candidates": cands[:8]}


def resync(seq):
    """Индексы, где последовательность номеров ломается.

    Используется QA и маргинальным режимом: разрыв — это либо перезапуск
    нумерации в новом разделе, либо пропущенная единица. Различать их
    механически нельзя, поэтому оба случая идут в отчёт.
    """
    breaks = []
    for i, (a, b) in enumerate(zip(seq, seq[1:])):
        if b != a + 1:
            breaks.append({"at": i + 1, "prev": a, "next": b,
                           "kind": "restart" if b < a else ("gap" if b > a + 1 else "duplicate")})
    return breaks


# ---------- служебное ----------

def load_profile(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        prof = yaml.safe_load(f)
    if "unit" in prof and "units" not in prof:      # профиль первого поколения
        prof["units"] = [dict(prof["unit"], mode=prof["unit"].get("mode", "flow"))]
    prof.setdefault("units", [])
    for u in prof["units"]:
        u.setdefault("mode", "flow")
    return prof


def compile_patterns(pats):
    return [re.compile(p, re.IGNORECASE) for p in (pats or [])]


def find_all(patterns, text):
    seen, out = set(), []
    for rx in patterns:
        for m in rx.finditer(text):
            v = re.sub(r"\s+", " ", m.group(0)).strip()
            if v.lower() not in seen:
                seen.add(v.lower())
                out.append(v)
    return out
