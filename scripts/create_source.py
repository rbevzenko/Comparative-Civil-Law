#!/usr/bin/env python3
"""Регистрация книги в сервисе: метаданные + PDF в объектное хранилище.

    python scripts/create_source.py --meta books/<id>/meta.json --pdf книга.pdf \
        --base-url https://host --env-file ~/.corpus.env [--dry-run]

Печатает `source_id` — его и надо передать в upload_corpus.py.

Реквизиты берутся из того же `meta.json`, по которому нарезаны карточки: если
источник в сервисе и корпус разойдутся в годе издания или в составе авторов,
это разойдётся и в сносках, а заметить будет негде.

Файл уходит в объектное хранилище через сервис, а не мимо него: presigned-
ссылку на PDF потом выдаёт он же, и ключ объекта должен знать он, а не мы.

Повторный запуск создаёт ВТОРОЙ источник — у `POST /sources` нет ключа
идемпотентности. Поэтому скрипт сначала ищет источник с тем же названием и
годом и отказывается работать, если нашёл: чинить раздвоенную книгу дороже,
чем перечитать сообщение.
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid


def request(url, token, data=None, headers=None, method=None, timeout=600):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} от {url}: {e.read().decode()[:600]}")


def multipart(fields, file_field, file_path):
    """Тело multipart/form-data: сервис принимает источник только так."""
    boundary = uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        if value is None or value == "":
            continue
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n").encode()
    ctype = mimetypes.guess_type(file_path)[0] or "application/pdf"
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{os.path.basename(file_path)}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    with open(file_path, "rb") as fh:
        out += fh.read()
    out += f"\r\n--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--env-file")
    ap.add_argument("--source-type", default="textbook", choices=["textbook", "commentary"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="создать, даже если похожий источник уже есть")
    a = ap.parse_args()

    env = dict(os.environ)
    if a.env_file:
        path = os.path.expanduser(a.env_file)
        if not os.path.exists(path):
            raise SystemExit(f"нет файла с ключами: {path}")
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    token = env.get("API_TOKEN")
    if not token:
        raise SystemExit("нет API_TOKEN ни в окружении, ни в --env-file")

    meta = json.load(open(a.meta, encoding="utf-8"))
    fields = {
        "title": meta["title"],
        "jurisdiction": meta["jurisdiction"],
        "source_type": a.source_type,
        "authors": "; ".join(meta.get("authors") or []),
        "edition": meta.get("edition"),
        "year": meta.get("year"),
        "publisher": meta.get("publisher"),
        "language": meta.get("language"),
        "pdf_pages_total": meta.get("pdf_pages_total"),
    }
    size = os.path.getsize(a.pdf)
    print("реквизиты источника:")
    for k, v in fields.items():
        print(f"  {k:16s} {v}")
    print(f"  PDF              {os.path.basename(a.pdf)}, {size / 1e6:.1f} МБ")

    base = a.base_url.rstrip("/")
    existing = request(f"{base}/sources?limit=200", token)
    twins = [s for s in existing.get("items", [])
             if s["title"].strip().lower() == meta["title"].strip().lower()
             and s.get("year") == meta.get("year")]
    if twins and not a.force:
        print("\nТакой источник в сервисе уже есть — повтор создал бы вторую книгу:")
        for s in twins:
            print(f"  {s['id']}  {s['title'][:70]} ({s.get('year')})")
        print("Если это всё-таки другая книга, повторить с --force.")
        return

    if a.dry_run:
        print("\ndry-run: источник не создан")
        return

    body, ctype = multipart(fields, "pdf", a.pdf)
    created = request(f"{base}/sources", token, data=body,
                      headers={"Content-Type": ctype}, method="POST")
    print(f"\nsource_id: {created['id']}")
    print(f"страница источника: {base}/ui/sources/{created['id']}")
    print("Дальше: upload_corpus.py --source-id " + created["id"])


if __name__ == "__main__":
    main()
