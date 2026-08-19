#!/usr/bin/env python3
"""Загрузка нарезанной книги в сервис: эмбеддинги + POST /sources/{id}/chunks.

    python scripts/upload_corpus.py --upload books/<id>/output/upload.json \
        --source-id <uuid> --base-url https://host [--dry-run] [--limit N]

Недостающее звено между внешним пайплайном нарезки и хранилищем. API
эмбеддинги не считает намеренно (см. README, «Про размерность эмбеддинга»),
поэтому вектор считается здесь и приходит в теле запроса готовым.

Идемпотентность держится на external_id: повторный запуск того же файла
обновляет совпавшие карточки, а не плодит дубли, и внутренний uuid
фрагмента сохраняется — иначе умрут все ранее выданные universal_ref.

Секреты берутся из окружения (API_TOKEN, OPENAI_API_KEY) или из файла
`--env-file` в формате KEY=VALUE. Файл с ключами лежит вне репозитория и в
гит не попадает; в аргументах команды секретов нет намеренно — иначе они
оседают в истории оболочки и в журналах.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Управляющие символы, которые Postgres не принимает в text/jsonb. Чаще
# прочих приходит \x00: им набивают хвосты заголовков в оглавлении PDF, и
# приёмник отвечает на такую карточку голой 500 без объяснения.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"
# Предел эмбеддера — 8191 токен на вход. Символы к токенам на немецком идут
# примерно как 3:1, но у карточки со сносками бывает и хуже, поэтому режем с
# запасом: обрезка касается только вектора, текст в базу уходит целиком.
MAX_CHARS = 18000


class TooLarge(Exception):
    """Тело запроса не прошло через прокси перед сервисом."""


def post_chunks(url, items, token, limit=None):
    """Отправка карточек с делением пачки пополам при 413.

    Предел на размер тела стоит не в сервисе, а в прокси перед ним, и узнать
    его заранее неоткуда. Поэтому он нащупывается: пачка делится пополам,
    пока не пройдёт, и найденный размер запоминается на остаток загрузки.
    """
    try:
        post_json(url, {"chunks": items}, token)
        return limit or len(items)
    except TooLarge:
        if len(items) == 1:
            raise SystemExit(f"одна карточка {items[0]['external_id']} не лезет в предел прокси")
        half = len(items) // 2
        print(f"  тело велико, делю пачку {len(items)} → {half}", flush=True)
        found = post_chunks(url, items[:half], token, limit)
        return post_chunks(url, items[half:], token, min(found, half))


def post_json(url, payload, token, timeout=180, retries=4):
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:600]
            # 413 — единственный код, который лечится повтором меньшей пачкой:
            # перед сервисом стоит nginx со своим пределом на тело запроса, а
            # пачка из 64 карточек с векторами на 1536 весит около двух мегабайт.
            if e.code == 413:
                raise TooLarge(detail)
            # Остальные 4xx — наша ошибка в данных, повтор её не вылечит.
            if 400 <= e.code < 500:
                raise SystemExit(f"HTTP {e.code} от {url}: {detail}")
            last = f"HTTP {e.code}: {detail}"
        except Exception as e:                      # сеть, таймаут
            last = repr(e)
        time.sleep(2 ** attempt)
    raise SystemExit(f"{url} не ответил после {retries} попыток: {last}")


def embed(texts, key):
    payload = {"model": EMBEDDING_MODEL, "input": [t[:MAX_CHARS] for t in texts]}
    out = post_json("https://api.openai.com/v1/embeddings", payload, key)
    vecs = [d["embedding"] for d in sorted(out["data"], key=lambda d: d["index"])]
    if len(vecs) != len(texts):
        raise SystemExit(f"эмбеддер вернул {len(vecs)} векторов на {len(texts)} входов")
    for v in vecs:
        if len(v) != EMBEDDING_DIM:
            raise SystemExit(f"размерность {len(v)}, а колонка в базе — vector({EMBEDDING_DIM})")
    return vecs


def scrub(value, stats):
    """Чистит строки от управляющих символов, считая, сколько вычищено."""
    if isinstance(value, str):
        clean = CONTROL.sub("", value)
        if clean != value:
            stats["fields"] += 1
            stats["chars"] += len(value) - len(clean)
        return clean
    if isinstance(value, list):
        return [scrub(v, stats) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, stats) for k, v in value.items()}
    return value


def to_chunk(card):
    """Проекция пайплайна → ChunkCreate. Поля, которых нет в схеме приёмника,
    не выдумываются и не переименовываются: они остаются в cards.jsonl."""
    notes = []
    dropped = 0
    for fn in card.get("footnotes") or []:
        n = fn.get("number")
        text = (fn.get("text") or "").strip()
        if not text:
            continue
        # number в схеме приёмника целочисленный и обязательный: блок, у
        # которого номер не прочитан, молча терять нельзя, но и придумывать
        # ему номер тоже — он уйдёт в отчёт числом.
        try:
            notes.append({"number": int(n), "text": text})
        except (TypeError, ValueError):
            dropped += 1
    return {
        "external_id": card["external_id"],
        "citation": card["citation"],
        "point_number": card.get("unit_number"),
        "text": card["text"],
        "hierarchy": card.get("hierarchy") or [],
        "page_start": card.get("page_start"),
        "page_end": card.get("page_end"),
        "footnotes": notes,
    }, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", required=True, help="output/upload.json от upload_projection.py")
    ap.add_argument("--source-id", required=True, help="uuid источника, уже заведённого в сервисе")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--batch", type=int, default=32, help="карточек в одном POST (уменьшается сам, если прокси не пропускает)")
    ap.add_argument("--embed-batch", type=int, default=96)
    ap.add_argument("--limit", type=int, help="взять только первые N карточек (проверка тракта)")
    ap.add_argument("--dry-run", action="store_true", help="посчитать и проверить, ничего не грузить")
    ap.add_argument("--state", help="файл с уже загруженными external_id (докачка после обрыва)")
    ap.add_argument("--env-file", help="файл KEY=VALUE с API_TOKEN и OPENAI_API_KEY")
    a = ap.parse_args()

    env = dict(os.environ)
    if a.env_file:
        path = os.path.expanduser(a.env_file)
        if not os.path.exists(path):
            raise SystemExit(f"нет файла с ключами: {path}")
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")

    token = env.get("API_TOKEN")
    key = env.get("OPENAI_API_KEY")
    if not a.dry_run and not token:
        raise SystemExit("нет API_TOKEN в окружении")
    if not a.dry_run and not key:
        raise SystemExit("нет OPENAI_API_KEY в окружении")

    cards = json.load(open(a.upload, encoding="utf-8"))
    if a.limit:
        cards = cards[:a.limit]

    done = set()
    if a.state and os.path.exists(a.state):
        done = {l.strip() for l in open(a.state, encoding="utf-8") if l.strip()}
        cards = [c for c in cards if c["external_id"] not in done]
        print(f"уже загружено ранее: {len(done)}, осталось: {len(cards)}")

    items, dropped_notes = [], 0
    scrubbed = {"fields": 0, "chars": 0}
    for c in cards:
        it, d = to_chunk(c)
        it = scrub(it, scrubbed)
        dropped_notes += d
        if not it["text"].strip():
            raise SystemExit(f"пустой текст у {it['external_id']}")
        items.append(it)

    ids = [i["external_id"] for i in items]
    if len(set(ids)) != len(ids):
        raise SystemExit("external_id не уникальны внутри файла")

    total_notes = sum(len(i["footnotes"]) for i in items)
    print(f"карточек: {len(items)}, сносок: {total_notes}, "
          f"сносок без читаемого номера (не грузятся): {dropped_notes}")
    if scrubbed["fields"]:
        print(f"вычищено управляющих символов: {scrubbed['chars']} "
              f"в {scrubbed['fields']} полях")
    if a.dry_run:
        print("dry-run: ничего не отправлено")
        print(json.dumps(items[0] | {"text": items[0]["text"][:200] + "…"}, ensure_ascii=False, indent=1))
        return

    url = f"{a.base_url.rstrip('/')}/sources/{a.source_id}/chunks"
    state = open(a.state, "a", encoding="utf-8") if a.state else None
    sent, batch = 0, a.batch
    # Эмбеддинги считаются пачками покрупнее, чем идёт POST: у эмбеддера
    # накладные расходы на запрос, у приёмника — на размер тела.
    for s in range(0, len(items), a.embed_batch):
        block = items[s:s + a.embed_batch]
        vecs = embed([i["text"] for i in block], key)
        for i, v in zip(block, vecs):
            i["embedding"] = v
        b = 0
        while b < len(block):
            part = block[b:b + batch]
            batch = min(batch, post_chunks(url, part, token, batch))
            b += len(part)
            sent += len(part)
            if state:
                state.write("".join(i["external_id"] + "\n" for i in part))
                state.flush()
            print(f"  загружено {sent}/{len(items)}", flush=True)
    if state:
        state.close()
    print(f"Готово: {sent} карточек, модель эмбеддинга {EMBEDDING_MODEL}")


if __name__ == "__main__":
    main()
