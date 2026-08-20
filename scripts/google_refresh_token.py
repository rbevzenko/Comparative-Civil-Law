#!/usr/bin/env python3
"""Получение refresh-токена Google прямо на сервере, без OAuth Playground.

    python scripts/google_refresh_token.py --env-file .env [--write]

Playground оказался ненадёжным посредником: он выписывает код тому
клиенту, чьи ключи стояли в его настройках В МОМЕНТ нажатия «Authorize»,
и токен, полученный по умолчанию, к своему клиенту уже не подходит —
приём отвечает `invalid_grant` без объяснений. Плюс длинные строки в его
поле легко скопировать наполовину.

Здесь тот же обмен делается вручную: скрипт печатает ссылку, человек
открывает её в браузере и разрешает доступ, браузер приземляется на
страницу Playground с кодом в адресе — код оттуда вставляется обратно в
скрипт. Redirect_uri берётся тот же, что уже прописан у клиента в
консоли, — заводить второй не нужно.

`--write` дописывает GOOGLE_OAUTH_REFRESH_TOKEN в файл ключей, заменяя
прежнюю строку: так токен не проходит через буфер обмена вовсе.

Область доступа — `drive.file`: только то, что создано этим же клиентом.
Остальной Диск для него закрыт.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safeprint

_safeprint.install()

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REDIRECT = "https://developers.google.com/oauthplayground"
SCOPE = "https://www.googleapis.com/auth/drive.file"


def read_env(path):
    env = {}
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


def extract_code(raw):
    """Из вставленного принимается и голый код, и целый адрес страницы.

    После согласия браузер стоит на странице Playground, и человеку проще
    скопировать всю строку адреса, чем выцеливать в ней кусок. Код в
    адресе закодирован (`4%2F0A…`) — это тоже разбирается.
    """
    raw = raw.strip().strip("'\"")
    if raw.startswith("http"):
        query = urllib.parse.urlparse(raw).query
        got = urllib.parse.parse_qs(query).get("code")
        if not got:
            raise SystemExit("в этом адресе нет параметра code")
        return got[0]
    return urllib.parse.unquote(raw) if "%" in raw else raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--write", action="store_true", help="дописать токен в файл ключей")
    ap.add_argument(
        "--code",
        help="адрес приземления браузера (или голый код). Кладите в ОДИНАРНЫЕ кавычки: "
        "в адресе есть знак &, и без кавычек оболочка порвёт его на куски",
    )
    ap.add_argument("--url-only", action="store_true", help="только напечатать ссылку согласия")
    a = ap.parse_args()

    env = read_env(a.env_file)
    client_id = env.get("GOOGLE_OAUTH_CLIENT_ID")
    secret = env.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not secret:
        raise SystemExit("в файле ключей нет GOOGLE_OAUTH_CLIENT_ID и GOOGLE_OAUTH_CLIENT_SECRET")

    url = AUTH + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPE,
            # offline + consent: без них Google на повторном согласии
            # отдаёт только access-токен, а refresh-токен — единственное,
            # ради чего всё затевается.
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    if a.url_only:
        print(url)
        return

    if not a.code:
        print("\n1. Откройте эту ссылку в браузере (одной строкой, целиком):\n")
        print(url)
        print(
            "\n2. Войдите своим аккаунтом и разрешите доступ до конца: кнопок"
            "\n   «Continue»/«Allow» бывает две-три подряд. Если Google скажет, что"
            "\n   приложение не проверено: Advanced -> Go to ... (unsafe)."
            "\n3. Дождитесь, пока в адресной строке появится developers.google.com"
            "\n   и внутри будет code=… . Пока там accounts.google.com — рано."
            "\n4. Скопируйте ВЕСЬ адрес и выполните (кавычки обязательны):\n"
        )
        print(f"   python3 {sys.argv[0]} --env-file {a.env_file} --write \\")
        print("       --code 'СЮДА_АДРЕС'\n")
        return
    code = extract_code(a.code)

    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
        }
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN, data=data), timeout=60) as r:
            got = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(
            f"обмен не прошёл: HTTP {e.code} {body}\n"
            "invalid_grant тут значит, что код уже использован или устарел — "
            "запустите скрипт заново и пройдите ссылку ещё раз."
        )

    token = got.get("refresh_token")
    if not token:
        raise SystemExit(
            "Google не выдал refresh_token. Так бывает, когда согласие уже давалось: "
            "зайдите на myaccount.google.com/permissions, уберите это приложение и повторите."
        )

    if a.write:
        path = os.path.expanduser(a.env_file)
        lines = [
            l for l in open(path, encoding="utf-8").read().splitlines()
            if not l.startswith("GOOGLE_OAUTH_REFRESH_TOKEN=")
        ]
        lines.append(f"GOOGLE_OAUTH_REFRESH_TOKEN={token}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nготово: refresh-токен записан в {path} (длина {len(token)})")
    else:
        print(f"\nrefresh-токен (длина {len(token)}):\n{token}")


if __name__ == "__main__":
    main()
