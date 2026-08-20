#!/usr/bin/env python3
"""Сборка бэкапа: карточки, системные файлы приложения, выгрузка корпуса.

    python scripts/backup.py --out ~/backups \
        [--service-url https://… --env-file ~/.corpus.env] \
        [--include-dump ~/corpus-2026-08-20.dump] [--no-cards] [--no-system]

Бэкап нужен не «на всякий случай»: у тридцати одного источника австрийского
корпуса нет ни каталога в `books/`, ни PDF — единственная копия лежит в
базе сервиса (см. docs/service-todo.md, пункт 7). А в июне двенадцать книг
остались без `cards.jsonl.gz`, и прогон сборки текста затёр рабочую копию
без возможности отката (пункт 6). Обе беды — про отсутствие второй копии.

Набор складывается в каталог `comparative-civil-law-<дата>` и состоит из
четырёх частей, каждая самостоятельна:

* `system.tar.gz` — код приложения, миграции, скрипты, конфигурация
  развёртывания, скиллы, документация. Всё, что нужно, чтобы поднять
  сервис с нуля. Секретов здесь нет: `.env` в гит не попадает и в архив
  не кладётся, лежит только `.env.example`.
* `cards.tar.gz` — всё содержимое `books/`, попавшее в репозиторий:
  `cards.jsonl.gz` каждой книги, `meta.json`, профили нарезки и отчёты о
  качестве. Кэш растров и OCR не кладутся: они воспроизводятся из PDF.
* `corpus/` — выгрузка сервиса по API: список источников и чанки со
  сносками, по файлу на источник. Единственный способ достать те
  тридцать один источник, которых в репозитории нет вовсе.
* `MANIFEST.txt` и `SHA256SUMS` — что именно лежит в наборе, сколько
  карточек, чем восстанавливать.

ВАЖНО про выгрузку по API: эмбеддингов в ней НЕТ — `ChunkRead` их не
отдаёт. Восстановление из `corpus/` вернёт текст, иерархию и сноски, но
векторы придётся считать заново (`upload_corpus.py` это и делает). Полная
копия вместе с векторами снимается только на хосте: `pg_dump` и потом
`--include-dump`, чтобы файл лёг в тот же набор и в тот же манифест.

Секреты берутся из `--env-file` в формате KEY=VALUE и в аргументы команды
не попадают: иначе они оседают в истории оболочки и в журналах.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import datetime
import gzip
import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Страница выгрузки чанков. Двести штук со сносками — это единицы мегабайт
# на ответ: больше упирается в память приёмника, меньше — в число запросов.
PAGE = 200


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


def tracked(prefix=None, exclude=None):
    """Состав архива — по списку файлов гита, а не по обходу каталога.

    Так в бэкап не попадают ни кэш растров, ни `.venv`, ни `.env`: что
    исключено из репозитория, исключено и здесь, одним правилом на оба
    места.
    """
    out = subprocess.run(
        ["git", "-C", REPO, "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    files = [f for f in out.decode().split("\0") if f]
    if prefix:
        files = [f for f in files if f.startswith(prefix)]
    if exclude:
        files = [f for f in files if not f.startswith(exclude)]
    return sorted(files)


def make_tar(dest, files):
    """tar из списка файлов: имена приходят через stdin, а не через argv.

    Четыреста семьдесят путей в командной строке ещё пролезут, но список
    растёт с каждой книгой, и упереться в предел длины аргументов посреди
    бэкапа — худшее место для такой ошибки.
    """
    p = subprocess.run(
        ["tar", "czf", dest, "-C", REPO, "--null", "--files-from=-"],
        input="\0".join(files).encode(),
        capture_output=True,
    )
    if p.returncode != 0:
        raise SystemExit(f"tar не собрался: {p.stderr.decode().strip()}")
    return os.path.getsize(dest)


def fetch(url, token, tries=4):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 4xx не лечится повтором: не тот токен, не тот адрес, нет
            # источника. Повторять стоит только временный отказ сервиса.
            if e.code < 500 or attempt == tries - 1:
                raise SystemExit(f"{url}: HTTP {e.code} {e.read()[:200].decode(errors='replace')}")
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def slug(source):
    """Имя файла источника: внешний ключ книги, иначе uuid.

    По `external_id` карточек видно, из какой книги источник, — но у
    источника своего ключа нет, поэтому берём заголовок. Заголовок бывает
    длинным и с двоеточиями, так что чистим его до имени файла.
    """
    base = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in source.get("title", "")
    ).strip("-").lower()
    base = "-".join(x for x in base.split("-") if x)[:60]
    return f"{base or 'source'}-{source['id'][:8]}"


def dump_corpus(out_dir, base_url, token):
    """Выгрузка сервиса: список источников и чанки со сносками.

    `?with_footnotes=true` обязателен: приём заменяет набор сносок целиком,
    и восстановление из выгрузки без сносок оставило бы корпус без них.
    """
    os.makedirs(out_dir, exist_ok=True)
    base = base_url.rstrip("/")

    sources, offset = [], 0
    while True:
        page = fetch(f"{base}/sources?limit=100&offset={offset}", token)
        sources.extend(page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break
    with open(os.path.join(out_dir, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)
    print(f"источников: {len(sources)}")

    stats = []
    for i, s in enumerate(sources, 1):
        name = slug(s)
        path = os.path.join(out_dir, f"{name}.jsonl.gz")
        got, offset, total = 0, 0, None
        with gzip.open(path, "wt", encoding="utf-8") as f:
            while True:
                page = fetch(
                    f"{base}/sources/{s['id']}/chunks"
                    f"?limit={PAGE}&offset={offset}&with_footnotes=true",
                    token,
                )
                total = page["total"]
                for chunk in page["items"]:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                got += len(page["items"])
                offset += len(page["items"])
                if got >= total or not page["items"]:
                    break
        stats.append({"source": s.get("title", ""), "file": f"{name}.jsonl.gz", "chunks": got})
        print(f"[{i}/{len(sources)}] {s.get('title', '')[:60]}: {got} чанков")
        if total is not None and got != total:
            print(f"!! {name}: получено {got}, сервис насчитал {total}")
    return sources, stats


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="каталог, куда сложить набор")
    ap.add_argument("--service-url", help="база API сервиса, например https://host")
    ap.add_argument("--env-file", help="файл KEY=VALUE с API_TOKEN")
    ap.add_argument("--include-dump", help="готовый pg_dump — положить в набор")
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--no-system", action="store_true")
    ap.add_argument("--no-corpus", action="store_true")
    a = ap.parse_args()

    day = datetime.date.today().isoformat()
    root = os.path.join(os.path.expanduser(a.out), f"comparative-civil-law-{day}")
    os.makedirs(root, exist_ok=True)
    parts, notes = [], []

    if not a.no_system:
        files = tracked(exclude="books/")
        size = make_tar(os.path.join(root, "system.tar.gz"), files)
        parts.append(("system.tar.gz", size, f"{len(files)} файлов приложения"))
        print(f"system.tar.gz: {len(files)} файлов, {human(size)}")

    if not a.no_cards:
        files = tracked(prefix="books/")
        size = make_tar(os.path.join(root, "cards.tar.gz"), files)
        books = len({f.split("/")[1] for f in files})
        parts.append(("cards.tar.gz", size, f"{books} книг, {len(files)} файлов"))
        print(f"cards.tar.gz: {books} книг, {len(files)} файлов, {human(size)}")

    corpus_stats = []
    if not a.no_corpus and a.service_url:
        if not a.env_file:
            raise SystemExit("--service-url без --env-file: нечем авторизоваться")
        token = read_env(a.env_file).get("API_TOKEN")
        if not token:
            raise SystemExit("в файле с ключами нет API_TOKEN")
        sources, corpus_stats = dump_corpus(os.path.join(root, "corpus"), a.service_url, token)
        total = sum(s["chunks"] for s in corpus_stats)
        notes.append(
            f"corpus/: {len(sources)} источников, {total} чанков — БЕЗ векторов, "
            "при восстановлении эмбеддинги считаются заново"
        )
    elif not a.no_corpus:
        notes.append("corpus/: выгрузка не делалась — не задан --service-url")

    if a.include_dump:
        src = os.path.expanduser(a.include_dump)
        dest = os.path.join(root, os.path.basename(src))
        shutil.copy2(src, dest)
        parts.append((os.path.basename(src), os.path.getsize(dest), "pg_dump, векторы внутри"))
        print(f"{os.path.basename(src)}: {human(os.path.getsize(dest))}")

    files_on_disk = []
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            if n in ("MANIFEST.txt", "SHA256SUMS"):
                continue
            p = os.path.join(dirpath, n)
            files_on_disk.append((os.path.relpath(p, root), p))
    files_on_disk.sort()

    with open(os.path.join(root, "SHA256SUMS"), "w", encoding="utf-8") as f:
        for rel, p in files_on_disk:
            f.write(f"{sha256(p)}  {rel}\n")

    total_size = sum(os.path.getsize(p) for _, p in files_on_disk)
    with open(os.path.join(root, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        f.write(f"Бэкап Comparative Civil Law\nСнят: {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        head = subprocess.run(
            ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        f.write(f"Коммит репозитория: {head}\n")
        f.write(f"Всего файлов: {len(files_on_disk)}, объём: {human(total_size)}\n\n")
        f.write("Состав\n")
        for name, size, what in parts:
            f.write(f"  {name}: {human(size)} — {what}\n")
        for stat in corpus_stats:
            f.write(f"  corpus/{stat['file']}: {stat['chunks']} чанков — {stat['source']}\n")
        if notes:
            f.write("\nОговорки\n")
            for n in notes:
                f.write(f"  {n}\n")
        f.write(
            "\nВосстановление\n"
            "  system.tar.gz — распаковать, положить рядом .env (см. .env.example),\n"
            "    docker compose up -d --build, alembic upgrade head.\n"
            "  cards.tar.gz — распаковать в корень репозитория; дальше\n"
            "    upload_projection.py и scripts/upload_corpus.py по книге,\n"
            "    либо scripts/reupload_all.py разом.\n"
            "  corpus/*.jsonl.gz — текст, иерархия и сноски без векторов;\n"
            "    залить обратно можно через upload_corpus.py, эмбеддинги\n"
            "    он считает сам.\n"
            "  pg_dump — pg_restore в чистую базу: единственный путь, который\n"
            "    возвращает векторы без пересчёта.\n"
        )
    print(f"\nнабор собран: {root}\nфайлов {len(files_on_disk)}, объём {human(total_size)}")
    print(open(os.path.join(root, "MANIFEST.txt"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
