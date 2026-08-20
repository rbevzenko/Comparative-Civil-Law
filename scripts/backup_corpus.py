#!/usr/bin/env python3
"""Резервная выгрузка корпуса из сервиса в файлы.

    python scripts/backup_corpus.py --base-url https://… --env-file ~/.corpus.env \
        --out archive [--only <uuid> …] [--with-footnotes auto|yes|no]

Зачем. Карточки тридцати восьми книг лежат в репозитории (`books/*/output/
cards.jsonl.gz`) и воспроизводимы из PDF и профиля. Тридцать один источник
австрийского корпуса заведён раньше нынешнего пайплайна: ни каталога, ни
карточек, ни PDF — он существует ТОЛЬКО в базе сервиса. Потеря машины
означала бы потерю этих текстов насовсем.

Что выгружается. Всё, что отдаёт API: реквизиты источника, текст чанка,
иерархия, номера страниц, сноски. Эмбеддинги API не отдаёт вовсе — и это
не страшно: пересчёт всего корпуса по text-embedding-3-small стоит меньше
доллара. Настоящий дамп базы вместе с векторами снимается на самой машине
через `pg_dump` — см. `docs/backup.md`.

Сноски. `?with_footnotes=true` появился позже части развёртываний. Режим
`auto` проверяет поддержку на первой же странице и, если её нет, честно
пишет в манифест, что сноски не выгружены, вместо того чтобы делать по
запросу на чанк (на тридцати тысячах чанков это тридцать тысяч запросов).

Секреты берутся из `--env-file` и в аргументы команды не попадают.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import gzip
import json
import re
import time
import urllib.error
import urllib.request


def read_env(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise SystemExit(f"нет файла с ключами: {path}")
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def fetch(url, token, tries=4):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def slug(s, n=60):
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"[\s_]+", "-", s).lower()
    return s[:n].strip("-") or "source"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--out", required=True, help="каталог выгрузки")
    ap.add_argument("--only", nargs="*", help="только эти uuid источников")
    ap.add_argument("--with-footnotes", default="auto", choices=("auto", "yes", "no"))
    ap.add_argument("--page", type=int, default=200)
    a = ap.parse_args()

    token = read_env(a.env_file).get("API_TOKEN")
    if not token:
        raise SystemExit("в файле ключей нет API_TOKEN")
    base = a.base_url.rstrip("/")
    os.makedirs(a.out, exist_ok=True)

    sources = fetch(f"{base}/sources?limit=500", token)
    sources = sources.get("items", sources) if isinstance(sources, dict) else sources
    if a.only:
        sources = [s for s in sources if s["id"] in a.only]
    with open(os.path.join(a.out, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)
    print(f"источников: {len(sources)}")

    want_fn = a.with_footnotes != "no"
    fn_supported = None if a.with_footnotes == "auto" else (a.with_footnotes == "yes")
    rows, grand, no_fn = [], 0, []

    for s in sources:
        name = f"{slug(s['jurisdiction'])}--{slug(s['title'])}--{s['id'][:8]}"
        path = os.path.join(a.out, f"{name}.jsonl.gz")
        offset, total, got, notes = 0, None, 0, 0
        with gzip.open(path, "wt", encoding="utf-8") as out:
            while True:
                url = f"{base}/sources/{s['id']}/chunks?limit={a.page}&offset={offset}"
                if want_fn and fn_supported is not False:
                    url += "&with_footnotes=true"
                page = fetch(url, token)
                items, total = page["items"], page["total"]
                if fn_supported is None and items:
                    fn_supported = "footnotes" in items[0]
                    if not fn_supported:
                        print("  ВНИМАНИЕ: сервис не отдаёт сноски списком "
                              "(?with_footnotes не поддержан) — выгружаю без них")
                if not items:
                    break
                for it in items:
                    notes += len(it.get("footnotes") or [])
                    out.write(json.dumps(it, ensure_ascii=False) + "\n")
                got += len(items)
                offset += len(items)
                if offset >= total:
                    break
        size = os.path.getsize(path)
        grand += got
        if want_fn and not fn_supported:
            no_fn.append(s["id"])
        rows.append((s, name, got, total, notes, size))
        print(f"  {got:6d}/{total:<6d} сносок {notes:6d}  {size/1024:8.0f} КБ  {s['title'][:50]}")

    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines = [
        "# Резервная выгрузка корпуса",
        "",
        f"Снята: {stamp}. Сервис: {base}.",
        f"Источников: {len(rows)}, чанков: {grand}.",
        "",
        "Эмбеддинги СЮДА НЕ ВХОДЯТ — API их не отдаёт. Пересчитываются из",
        "текста моделью `text-embedding-3-small` (весь корпус — меньше доллара).",
        "Полный дамп базы вместе с векторами снимается на машине сервиса:",
        "см. `docs/backup.md`.",
        "",
    ]
    if no_fn:
        lines += [f"СНОСКИ НЕ ВЫГРУЖЕНЫ: сервис не поддерживает `?with_footnotes=true`. "
                  f"Затронуто источников: {len(no_fn)}.", ""]
    lines += ["| Чанков | Сносок | Размер | Юрисдикция | Источник | Файл |",
              "|---|---|---|---|---|---|"]
    for s, name, got, total, notes, size in sorted(rows, key=lambda r: -r[2]):
        warn = "" if got == total else f" (из {total}!)"
        lines.append(f"| {got}{warn} | {notes} | {size//1024} КБ | {s['jurisdiction']} | "
                     f"{s['title'][:70]} | `{name}.jsonl.gz` |")
    with open(os.path.join(a.out, "MANIFEST.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nВсего чанков: {grand}. Записано в {a.out}/ (+ sources.json, MANIFEST.md)")


if __name__ == "__main__":
    main()
