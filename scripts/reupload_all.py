#!/usr/bin/env python3
"""Перезаливка всего корпуса: проекция + загрузка по каждой книге подряд.

    python scripts/reupload_all.py --base-url https://… --env-file ~/.corpus.env \
        [--only <book_id> …] [--skip <book_id> …] [--dry-run]

Нужна, когда меняется не одна книга, а сквозное правило: собран текст
карточек, добавлено поле, переписан шаблон цитаты. Поштучно это тридцать
восемь команд, в каждой свой uuid, и ошибиться в одном — значит залить книгу
в чужой источник.

Порядок внутри книги тот же, что вручную: `upload_projection.py --force`
собирает `output/upload.json` из `output/cards.jsonl`, затем
`upload_corpus.py` считает эмбеддинги и грузит. Загрузка идемпотентна по
`external_id`: карточка с тем же ключом обновляется, а не задваивается.

Книги идут от МЕНЬШЕЙ к БОЛЬШЕЙ. Если тракт сломан — упрётся на первой сотне
карточек, а не после часа работы на Insolvenzordnung.

Секреты берутся из `--env-file` и в аргументы команды не попадают: иначе они
оседают в истории оболочки и в журналах.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import glob
import json
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = "/root/.claude/skills/synced/complaw-corpus/scripts"


def books(a):
    out = []
    for d in sorted(glob.glob("books/*")):
        if not os.path.isdir(d):
            continue
        b = os.path.basename(d)
        if a.only and b not in a.only:
            continue
        if b in (a.skip or []):
            continue
        meta_path = os.path.join(d, "meta.json")
        if not os.path.exists(meta_path):
            print(f"!! {b}: нет meta.json — пропущено")
            continue
        meta = json.load(open(meta_path, encoding="utf-8"))
        sid = meta.get("service_source_id")
        if not sid:
            print(f"!! {b}: нет service_source_id — пропущено")
            continue
        cards = os.path.join(d, "output", "cards.jsonl")
        if not os.path.exists(cards):
            print(f"!! {b}: нет output/cards.jsonl — пропущено")
            continue
        out.append((b, d, sid, sum(1 for _ in open(cards, encoding="utf-8"))))
    out.sort(key=lambda r: r[3])
    return out


def run(cmd, log):
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--only", nargs="*", help="только эти книги")
    ap.add_argument("--skip", nargs="*", help="кроме этих книг")
    ap.add_argument("--log-dir", default="/tmp/reupload", help="куда класть журналы прогонов")
    ap.add_argument("--dry-run", action="store_true", help="показать план и не грузить")
    a = ap.parse_args()

    plan = books(a)
    total = sum(n for *_, n in plan)
    print(f"Книг: {len(plan)}, карточек: {total}")
    for b, _, sid, n in plan:
        print(f"  {n:6d}  {b:34s} {sid}")
    if a.dry_run:
        print("dry-run: ничего не загружено")
        return

    os.makedirs(a.log_dir, exist_ok=True)
    done = failed = 0
    started = time.time()
    for b, d, sid, n in plan:
        print(f"\n== {b} ({n} карточек)")
        rc = run([sys.executable, os.path.join(SKILL, "upload_projection.py"),
                  "--book", d, "--force"], os.path.join(a.log_dir, f"{b}.proj.log"))
        if rc:
            print(f"  !! проекция не собралась, см. {a.log_dir}/{b}.proj.log")
            failed += 1
            continue
        rc = run([sys.executable, os.path.join(HERE, "upload_corpus.py"),
                  "--upload", os.path.join(d, "output", "upload.json"),
                  "--source-id", sid, "--base-url", a.base_url,
                  "--env-file", a.env_file], os.path.join(a.log_dir, f"{b}.up.log"))
        tail = ""
        log = os.path.join(a.log_dir, f"{b}.up.log")
        if os.path.exists(log):
            lines = [l.strip() for l in open(log, encoding="utf-8") if l.strip()]
            tail = lines[-1] if lines else ""
        if rc:
            print(f"  !! загрузка не прошла: {tail}")
            failed += 1
            continue
        done += 1
        mins = (time.time() - started) / 60
        print(f"  {tail}  [{done}/{len(plan)}, {mins:.0f} мин]")

    print(f"\nЗагружено книг: {done}, с ошибкой: {failed}, за {(time.time()-started)/60:.0f} мин")
    if failed:
        sys.exit(f"Не все книги залиты. Журналы в {a.log_dir}")


if __name__ == "__main__":
    main()
