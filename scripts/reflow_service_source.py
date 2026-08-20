#!/usr/bin/env python3
"""Сборка текста у источника, которого нет в репозитории.

    python scripts/reflow_service_source.py --source-id <uuid> --lang de \
        --base-url https://… --env-file ~/.corpus.env --out /tmp/x.json

Тридцать один источник австрийского корпуса заведён раньше нынешнего
пайплайна: карточек в `books/` нет, восстановить их нечем. Текст при этом
лежит в сервисе ровно таким, каким его нарезали, — с переносами по ширине
полосы, разорванными словами и неразрывными пробелами.

Скрипт читает чанки постранично (`?with_footnotes=true` — иначе приём
затрёт сноски: он заменяет их набор целиком), собирает текст тем же
`reflow_card_text.reflow`, и пишет файл в формате `output/upload.json`.
Дальше — обычный `upload_corpus.py`: эмбеддинги считаются заново, чанки
обновляются по `external_id`.

Чанк БЕЗ external_id пропускается: сопоставить его не с чем, и загрузка
завела бы дубль вместо обновления.

Секреты берутся из `--env-file` и в аргументы команды не попадают.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import importlib.util
import json
import time
import urllib.error
import urllib.request

_spec = importlib.util.spec_from_file_location(
    "reflow_card_text", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reflow_card_text.py")
)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def read_env(path):
    env = dict(os.environ)
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


def fetch(url, token, tries=4):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--lang", default="de", choices=sorted(R.SUSPENDED))
    ap.add_argument("--out", required=True, help="куда положить upload.json")
    ap.add_argument("--page", type=int, default=200)
    a = ap.parse_args()

    token = read_env(a.env_file).get("API_TOKEN")
    if not token:
        raise SystemExit("в файле ключей нет API_TOKEN")
    suspended = R.SUSPENDED[a.lang]

    base = a.base_url.rstrip("/")
    out, offset, total = [], 0, None
    changed = notes = heads = skipped = 0
    while True:
        page = fetch(f"{base}/sources/{a.source_id}/chunks"
                     f"?limit={a.page}&offset={offset}&with_footnotes=true", token)
        items = page["items"]
        total = page["total"]
        if not items:
            break
        for it in items:
            if not it.get("external_id"):
                skipped += 1
                continue
            text = it.get("text") or ""
            new = R.reflow(text, suspended)
            if new != text:
                changed += 1
            hierarchy = []
            for node in it.get("hierarchy") or []:
                nn = R.reflow(node, suspended)
                heads += nn != node
                hierarchy.append(nn)
            fns = []
            for fn in it.get("footnotes") or []:
                ft = fn.get("text") or ""
                nt = R.reflow(ft, suspended)
                notes += nt != ft
                fns.append({"number": fn.get("number"), "text": nt})
            out.append({
                "external_id": it["external_id"],
                "citation": it["citation"],
                "unit_number": it.get("point_number"),
                "text": new,
                "hierarchy": hierarchy,
                "page_start": it.get("page_start"),
                "page_end": it.get("page_end"),
                "printed_page_start": it.get("printed_page_start"),
                "printed_page_end": it.get("printed_page_end"),
                "footnotes": fns,
            })
        offset += len(items)
        print(f"  прочитано {offset}/{total}")
        if offset >= total:
            break

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"чанков: {len(out)}, собран текст у {changed}, сносок {notes}, узлов иерархии {heads}"
          + (f", пропущено без external_id: {skipped}" if skipped else ""))
    print(f"Записано: {a.out}")
    print(f"Дальше: upload_corpus.py --upload {a.out} --source-id {a.source_id}")


if __name__ == "__main__":
    main()
