#!/usr/bin/env python3
"""Удаление источника из сервиса вместе со всеми его фрагментами.

    python scripts/delete_source.py --source-id UUID --base-url URL \
        --env-file /home/user/.corpus.env [--yes]

Нужно там, где источник заведён по ошибке: файл оказался не той книгой,
нарезка пошла не по той единице, книга загружена дважды.

Операция НЕОБРАТИМА. Поэтому по умолчанию скрипт только показывает, что
собирается удалить — реквизиты источника и число фрагментов, — и требует
`--yes`, чтобы выполнить. Восстановить источник можно лишь повторной
загрузкой из локальных карточек, и то с новым идентификатором.

Токен читается из файла окружения, а не из аргументов: в аргументах он
осел бы в истории оболочки и в журналах.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_env_file(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def request(url, token, method="GET"):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
        return r.status, (json.loads(body) if body else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--yes", action="store_true",
                    help="выполнить удаление; без него скрипт только показывает, что удалит")
    a = ap.parse_args()

    env = read_env_file(a.env_file)
    token = env.get("API_TOKEN")
    if not token:
        sys.exit(f"в {a.env_file} нет API_TOKEN")

    base = a.base_url.rstrip("/")
    try:
        _, src = request(f"{base}/sources/{a.source_id}", token)
    except urllib.error.HTTPError as e:
        sys.exit(f"источник не найден: {e.code}")

    authors = ", ".join(src.get("authors") or []) or "—"
    print("Будет удалён источник:")
    print(f"  {authors}. {src.get('title')}")
    print(f"  {src.get('publisher') or '—'}, {src.get('year') or '—'} | "
          f"юрисдикция {src.get('jurisdiction')} | id {src.get('id')}")
    print(f"  фрагментов: {src.get('chunk_count', '?')}")

    if not a.yes:
        print("\nЭто показ, а не удаление. Чтобы удалить, повторите с --yes.")
        return

    status, _ = request(f"{base}/sources/{a.source_id}", token, method="DELETE")
    print(f"\nудалено, код ответа {status}")


if __name__ == "__main__":
    main()
