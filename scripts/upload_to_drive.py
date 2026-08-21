#!/usr/bin/env python3
"""Заливка файлов бэкапа в папку Google Drive.

    python scripts/upload_to_drive.py --folder-name "Comparative Civil Law" \
        --subfolder comparative-civil-law-2026-08-20 --env-file .env \
        /root/backups/comparative-civil-law-2026-08-20

Вторая копия имеет смысл только там, где не лежит первая: карточки и код
живут в гите, поэтому набор уходит наружу, в папку Диска.

Папка задаётся одним из двух ключей. `--folder-id` — по идентификатору из
адреса папки (drive.google.com/drive/folders/<id>); годится, когда ключ
открывает весь Диск. `--folder-name` — по имени: скрипт заведёт папку в
корне Диска сам, и это ЕДИНСТВЕННЫЙ рабочий путь для scope `drive.file`,
на котором стоит бэкап по расписанию. Такой ключ видит только созданное им
же, и заливка в сделанную руками папку падает с 404 «файл не найден».
Заведённую скриптом папку человек может потом перетащить куда угодно —
доступа к своим файлам скрипт не теряет.

Авторизация — по одному из трёх наборов ключей в `--env-file`, первый
найденный и берётся:

    GOOGLE_OAUTH_ACCESS_TOKEN=ya29.…            разовая заливка, токен живёт час
    GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN   регулярный бэкап
    GOOGLE_SERVICE_ACCOUNT_FILE=/path/key.json  сервисный аккаунт

Сервисный аккаунт годится ТОЛЬКО с общим диском Google Workspace: своего
места на Диске у него нет, и заливка в папку личного аккаунта падает на
квоте («Service Accounts do not have storage quota»). Для личного gmail
берите refresh-токен.

Файл льётся возобновляемой сессией кусками по 8 МБ: обрыв на сороковом
мегабайте продолжается с места обрыва, а не с начала. Файл с тем же
именем в папке по умолчанию обновляется НОВОЙ ВЕРСИЕЙ (ссылка на файл не
меняется); `--keep-both` кладёт рядом второй, `--skip-existing` не трогает
вовсе.

Секреты берутся из `--env-file` и в аргументы команды не попадают: иначе
они оседают в истории оболочки и в журналах.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import base64
import json
import mimetypes
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FILES = "https://www.googleapis.com/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file"
# Кусок возобновляемой заливки. Google требует кратности 256 КБ у всех
# кусков, кроме последнего; 8 МБ — компромисс между числом запросов и
# объёмом, который теряется при обрыве.
CHUNK = 8 * 1024 * 1024


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


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{url}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")


def token_from_service_account(path):
    """JWT подписывается openssl: RSA в стандартной библиотеке нет.

    Ставить ради подписи `cryptography` не хочется — она тянет сборку, а
    openssl есть в любом образе, где есть curl.
    """
    key = json.load(open(os.path.expanduser(path), encoding="utf-8"))
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64url(
        json.dumps(
            {
                "iss": key["client_email"],
                "scope": SCOPE,
                "aud": TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }
        ).encode()
    )
    body = header + b"." + claims
    p = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", "-binary"],
        input=key["private_key"].encode() + b"\n" + body,
        capture_output=True,
    )
    # Ключ и подписываемое идут в один stdin: openssl читает ключ до конца
    # PEM, остальное — данные. Разделять их файлами значит класть закрытый
    # ключ на диск лишний раз.
    if p.returncode != 0:
        raise SystemExit(f"openssl не подписал JWT: {p.stderr.decode().strip()}")
    jwt = body + b"." + b64url(p.stdout)
    got = post_form(
        TOKEN_URL,
        {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt.decode()},
    )
    return got["access_token"]


def access_token(env):
    if env.get("GOOGLE_OAUTH_ACCESS_TOKEN"):
        return env["GOOGLE_OAUTH_ACCESS_TOKEN"]
    if env.get("GOOGLE_OAUTH_REFRESH_TOKEN"):
        got = post_form(
            TOKEN_URL,
            {
                "client_id": env["GOOGLE_OAUTH_CLIENT_ID"],
                "client_secret": env["GOOGLE_OAUTH_CLIENT_SECRET"],
                "refresh_token": env["GOOGLE_OAUTH_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
        )
        return got["access_token"]
    if env.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
        return token_from_service_account(env["GOOGLE_SERVICE_ACCOUNT_FILE"])
    raise SystemExit(
        "в файле с ключами нет ни GOOGLE_OAUTH_ACCESS_TOKEN, ни GOOGLE_OAUTH_REFRESH_TOKEN, "
        "ни GOOGLE_SERVICE_ACCOUNT_FILE"
    )


def api(url, token, method="GET", body=None, headers=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    head = {"Authorization": f"Bearer {token}"}
    if data:
        head["Content-Type"] = "application/json; charset=UTF-8"
    head.update(headers or {})
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers=head)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == tries - 1:
                return e.code, dict(e.headers), e.read()
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def find_folder(token, name, parent):
    """Найти или завести папку. Ищется только среди своих же файлов.

    Scope `drive.file` даёт доступ ТОЛЬКО к тому, что создано этим самым
    клиентом: чужая папка на Диске для него не существует, и заливка в неё
    по идентификатору падает с 404. Поэтому папку заводит сам скрипт.
    """
    q = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent}' in parents and trashed = false"
    )
    url = f"{FILES}?q={urllib.parse.quote(q)}&fields=files(id,name)&supportsAllDrives=true"
    code, _, raw = api(url, token)
    if code != 200:
        raise SystemExit(f"поиск папки: HTTP {code} {raw[:300].decode(errors='replace')}")
    found = json.loads(raw).get("files", [])
    if found:
        return found[0]["id"], False
    code, _, raw = api(
        f"{FILES}?fields=id&supportsAllDrives=true",
        token,
        method="POST",
        body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]},
    )
    if code not in (200, 201):
        raise SystemExit(f"папка не завелась: HTTP {code} {raw[:300].decode(errors='replace')}")
    return json.loads(raw)["id"], True


def find_existing(token, folder_id, name):
    q = f"name = '{name}' and '{folder_id}' in parents and trashed = false"
    url = f"{FILES}?q={urllib.parse.quote(q)}&fields=files(id,name,size)&supportsAllDrives=true"
    code, _, raw = api(url, token)
    if code != 200:
        raise SystemExit(f"поиск в папке: HTTP {code} {raw[:300].decode(errors='replace')}")
    return json.loads(raw).get("files", [])


def upload(path, token, folder_id, file_id=None):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"

    if file_id:
        url = f"{UPLOAD}/{file_id}?uploadType=resumable&supportsAllDrives=true"
        meta, method = {"name": name}, "PATCH"
    else:
        url = f"{UPLOAD}?uploadType=resumable&supportsAllDrives=true"
        meta, method = {"name": name, "parents": [folder_id]}, "POST"
    code, headers, raw = api(
        url,
        token,
        method=method,
        body=meta,
        headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)},
    )
    if code not in (200, 201) or "Location" not in headers:
        raise SystemExit(f"{name}: сессия не открылась, HTTP {code} {raw[:300].decode(errors='replace')}")
    session = headers["Location"]

    sent = 0
    with open(path, "rb") as f:
        while sent < size:
            f.seek(sent)
            block = f.read(CHUNK)
            end = sent + len(block) - 1
            req = urllib.request.Request(
                session,
                data=block,
                method="PUT",
                headers={
                    "Content-Length": str(len(block)),
                    "Content-Range": f"bytes {sent}-{end}/{size}",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    body = json.loads(r.read() or b"{}")
                    sent = size
                    return body
            except urllib.error.HTTPError as e:
                if e.code == 308:
                    # Кусок принят, файл ещё не целиком. Сколько именно
                    # дошло, говорит Range: продолжаем с него, а не с
                    # конца отправленного — иначе потерянный хвост куска
                    # утечёт в дыру посреди файла.
                    rng = e.headers.get("Range")
                    sent = int(rng.split("-")[1]) + 1 if rng else sent + len(block)
                    print(f"  {name}: {sent * 100 // size}%")
                    continue
                raise SystemExit(f"{name}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                # Обрыв сети: у сессии спрашиваем, сколько байт дошло, и
                # продолжаем оттуда. Ради этого заливка и возобновляемая.
                print(f"  {name}: обрыв ({e}), спрашиваю смещение")
                time.sleep(3)
                probe = urllib.request.Request(
                    session, data=b"", method="PUT", headers={"Content-Range": f"bytes */{size}"}
                )
                try:
                    with urllib.request.urlopen(probe, timeout=120) as r:
                        return json.loads(r.read() or b"{}")
                except urllib.error.HTTPError as pe:
                    if pe.code == 308:
                        rng = pe.headers.get("Range")
                        sent = int(rng.split("-")[1]) + 1 if rng else sent
                        continue
                    raise SystemExit(f"{name}: HTTP {pe.code} {pe.read()[:300].decode(errors='replace')}")
    return {}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder-id", help="папка по идентификатору из её адреса на Диске")
    ap.add_argument(
        "--folder-name",
        help="папка по имени: заводится в корне Диска, если её нет. Единственный "
        "путь для ключа со scope drive.file — чужую папку он не видит",
    )
    ap.add_argument("--subfolder", help="подпапка внутри целевой, например по дате набора")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--keep-both", action="store_true", help="не обновлять одноимённый, класть второй")
    ap.add_argument("--skip-existing", action="store_true", help="одноимённый не трогать вовсе")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for dirpath, _, names in os.walk(p):
                files.extend(os.path.join(dirpath, n) for n in sorted(names))
        elif os.path.exists(p):
            files.append(p)
        else:
            raise SystemExit(f"нет файла: {p}")

    if not a.folder_id and not a.folder_name:
        raise SystemExit("нужен либо --folder-id, либо --folder-name")

    token = access_token(read_env(a.env_file))
    folder_id = a.folder_id
    if not folder_id:
        folder_id, made = find_folder(token, a.folder_name, "root")
        print(f"папка «{a.folder_name}»: {'заведена' if made else 'нашлась'}, id {folder_id}")
    if a.subfolder:
        folder_id, made = find_folder(token, a.subfolder, folder_id)
        print(f"подпапка «{a.subfolder}»: {'заведена' if made else 'нашлась'}, id {folder_id}")

    total = sum(os.path.getsize(f) for f in files)
    print(f"файлов {len(files)}, объём {human(total)}")

    for i, path in enumerate(sorted(files), 1):
        name = os.path.basename(path)
        size = os.path.getsize(path)
        existing = find_existing(token, folder_id, name)
        if existing and a.skip_existing:
            print(f"[{i}/{len(files)}] {name}: уже есть, пропуск")
            continue
        file_id = existing[0]["id"] if existing and not a.keep_both else None
        print(f"[{i}/{len(files)}] {name}: {human(size)}" + (" (новая версия)" if file_id else ""))
        got = upload(path, token, folder_id, file_id)
        print(f"  готово: https://drive.google.com/file/d/{got.get('id', file_id)}")


if __name__ == "__main__":
    main()
