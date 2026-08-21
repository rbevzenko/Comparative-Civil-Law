#!/usr/bin/env python3
"""Дозаливка номеров печатных страниц в уже загруженный корпус.

    python scripts/patch_printed_pages.py --all --base-url https://host \
        --env-file ~/.corpus.env [--dry-run]
    python scripts/patch_printed_pages.py --book books/<id> --base-url ... --env-file ...

Колонки `printed_page_start` / `printed_page_end` появились в базе позже,
чем туда легла большая часть корпуса, поэтому у загруженных карточек они
пустые, хотя в файлах нарезки страницы есть. Перезаливать ради двух чисел
весь корпус — значит заново считать больше ста тысяч эмбеддингов; вместо
этого сервис принимает PATCH /sources/{id}/chunks, который правит реквизиты
и не трогает ни текст, ни вектор.

Адресация — по external_id, тому же ключу, что и при загрузке. Внутренние
uuid фрагментов не меняются, значит все ранее выданные universal_ref живут.

Секреты берутся из окружения (API_TOKEN) или из файла `--env-file` в
формате KEY=VALUE; в аргументах команды их нет намеренно — иначе они
оседают в истории оболочки и в журналах.
"""

import argparse
import glob
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BATCH = 500


def request_json(url, token, payload=None, method="GET", timeout=180, retries=4):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:600]
            # 4xx — ошибка в данных или в адресе, повтор её не вылечит.
            if 400 <= e.code < 500:
                raise SystemExit(f"HTTP {e.code} от {method} {url}: {detail}")
            last = f"HTTP {e.code}: {detail}"
        except Exception as e:                      # сеть, таймаут
            last = repr(e)
        time.sleep(2 ** attempt)
    raise SystemExit(f"{url} не ответил после {retries} попыток: {last}")


def read_env(path):
    env = dict(os.environ)
    if not path:
        return env
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise SystemExit(f"нет файла с ключами: {path}")
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def norm(text):
    """Строка для сличения: регистр, пробелы и пунктуация к общему виду.

    Пунктуация выброшена не для красоты: у одной и той же книги в карточке
    сервиса и в файле нарезки том обозначен по-разному — «Band I.» против
    «Band I:», — и по точному совпадению они не сходятся.
    """
    text = re.sub(r"[^0-9a-zA-Zа-яёА-ЯЁäöüßÄÖÜáéíóúàèìòùâêîôûçñ]+", " ", text or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def norm_authors(authors):
    """Авторы одной строкой. В сервисе они лежат то списком по одному, то
    единственной строкой через запятую — сличать можно только склеенными."""
    if isinstance(authors, str):
        authors = [authors]
    return norm(" ".join(authors or []))


def load_sources(base_url, token):
    """Каталог сервиса целиком: id по заголовку и по паре заголовок+авторы."""
    by_title, by_title_authors = {}, {}
    offset = 0
    while True:
        page = request_json(f"{base_url}/sources?limit=200&offset={offset}", token)
        items = page.get("items") or []
        for s in items:
            by_title.setdefault(norm(s["title"]), []).append(s["id"])
            key = (norm(s["title"]), norm_authors(s.get("authors")))
            by_title_authors.setdefault(key, []).append(s["id"])
        offset += len(items)
        if not items or offset >= page.get("total", 0):
            break
    return {"by_title": by_title, "by_title_authors": by_title_authors}


def resolve_source_id(book_dir, cards, catalogue):
    """source_id книги: сначала из файла, потом сличением заголовка.

    Файл `source_id.txt` пишет пайплайн, но у книг, загруженных до его
    появления, его нет. Для них остаётся заголовок — и совпасть он должен
    ровно один раз: два источника с одинаковым названием разрешать
    самовольно нельзя, такую книгу лучше пропустить с внятной жалобой.
    """
    path = os.path.join(book_dir, "source_id.txt")
    if os.path.exists(path):
        sid = open(path, encoding="utf-8").read().strip()
        if sid:
            return sid, None

    src = cards[0].get("source") or {}
    title = src.get("title")
    # Сначала заголовок с авторами: «Contract Law» в корпусе двое разных,
    # и по одному заголовку их не развести. Потом — только заголовок, на
    # случай расхождения в написании имён.
    hits = catalogue["by_title_authors"].get((norm(title), norm_authors(src.get("authors"))), [])
    if len(hits) != 1:
        hits = catalogue["by_title"].get(norm(title), [])
    if len(hits) == 1:
        # Запоминаем, чтобы следующий прогон не сличал заголовки заново.
        with open(path, "w", encoding="utf-8") as f:
            f.write(hits[0] + "\n")
        return hits[0], None
    if not hits:
        return None, f"нет источника с заголовком {title!r}"
    return None, f"заголовок {title!r} совпал с {len(hits)} источниками"


def load_cards(book_dir):
    """Карточки книги. None, если файла нарезки нет вовсе.

    Порядок источников не случаен: `upload.json` и распакованный
    `cards.jsonl` из гита исключены (см. .gitignore), а `cards.jsonl.gz` в
    нём лежит. То есть на свежем клоне работает только третий вариант — и
    он должен работать без предварительного прогона пайплайна.
    """
    out = os.path.join(book_dir, "output")
    upload = os.path.join(out, "upload.json")
    if os.path.exists(upload):
        return json.load(open(upload, encoding="utf-8"))
    plain = os.path.join(out, "cards.jsonl")
    if os.path.exists(plain):
        return [json.loads(l) for l in open(plain, encoding="utf-8") if l.strip()]
    packed = os.path.join(out, "cards.jsonl.gz")
    if os.path.exists(packed):
        with gzip.open(packed, "rt", encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    return None


def patch_book(book_dir, base_url, token, catalogue, dry_run):
    """Возвращает строку отчёта по одной книге."""
    name = os.path.basename(book_dir.rstrip("/"))
    cards = load_cards(book_dir)
    if cards is None:
        return f"{name}: пропуск, нет файла нарезки в output/"
    if not cards:
        return f"{name}: пропуск, файл нарезки пуст"

    sid, err = resolve_source_id(book_dir, cards, catalogue)
    if sid is None:
        return f"{name}: ПРОПУСК — {err}"

    items, no_pages = [], 0
    for c in cards:
        start, end = c.get("printed_page_start"), c.get("printed_page_end")
        if start is None and end is None:
            # Файл без колонцифры (e-book, выгрузка из Westlaw): печатной
            # страницы у карточки нет вовсе. Слать null незачем — в базе
            # там уже null, а разница между «нет» и «не залили» видна
            # только по книге целиком, не по карточке.
            no_pages += 1
            continue
        items.append({
            "external_id": c["external_id"],
            "printed_page_start": start,
            "printed_page_end": end,
        })

    if not items:
        return f"{name}: печатных страниц нет ни у одной из {len(cards)} карточек"
    if dry_run:
        return (f"{name}: {len(items)} карточек к правке, без страниц {no_pages}, "
                f"источник {sid} (dry-run)")

    url = f"{base_url}/sources/{sid}/chunks"
    updated = unchanged = 0
    missing = []
    for s in range(0, len(items), BATCH):
        part = items[s:s + BATCH]
        res = request_json(url, token, {"chunks": part}, method="PATCH")
        updated += res["updated"]
        unchanged += res["unchanged"]
        missing.extend(res["missing"])
    tail = f", не найдено в сервисе {len(missing)}" if missing else ""
    return (f"{name}: проставлено {updated}, уже совпадало {unchanged}, "
            f"без печатных страниц {no_pages}{tail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="каталог книги (books/<id>)")
    ap.add_argument("--all", action="store_true", help="все книги в books/")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file", help="файл KEY=VALUE с API_TOKEN")
    ap.add_argument("--dry-run", action="store_true", help="посчитать, ничего не править")
    a = ap.parse_args()

    if bool(a.book) == bool(a.all):
        raise SystemExit("нужен ровно один из --book и --all")

    token = read_env(a.env_file).get("API_TOKEN")
    if not token:
        raise SystemExit("нет API_TOKEN в окружении")
    base_url = a.base_url.rstrip("/")

    catalogue = load_sources(base_url, token)
    total = sum(len(v) for v in catalogue["by_title"].values())
    print(f"источников в сервисе: {total}")

    books = sorted(glob.glob("books/*/")) if a.all else [a.book]
    skipped = []
    for book in books:
        line = patch_book(book, base_url, token, catalogue, a.dry_run)
        print(line, flush=True)
        if "ПРОПУСК" in line:
            skipped.append(line)

    if skipped:
        print(f"\nне удалось сопоставить с источником: {len(skipped)}", file=sys.stderr)


if __name__ == "__main__":
    main()
