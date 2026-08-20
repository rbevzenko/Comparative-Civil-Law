# Бэкап корпуса и приложения

## Зачем

Второй копии до сих пор не было ни у чего, и это уже дважды больно ударило.

* Тридцать один источник австрийского корпуса — Klang Grosskommentar,
  Bankvertragsrecht, Rummel и прочие, 31 912 чанков — существует ТОЛЬКО в
  базе сервиса: каталогов в `books/` у них нет, PDF в контейнере не
  сохранились (см. `service-todo.md`, пункт 7). Падение диска на хосте —
  и восстанавливать нечем.
* Двенадцать книг лежали в репозитории без `cards.jsonl.gz`, единственной
  копией карточек была рабочая, и прогон сборки текста затёр её без
  возможности отката (пункт 6).

## Что кладётся в набор

`scripts/backup.py` собирает каталог `comparative-civil-law-<дата>`:

| Файл | Что внутри | Чем восстанавливается |
| --- | --- | --- |
| `system.tar.gz` | код приложения, миграции, скрипты, `docker-compose.yml`, `Caddyfile`, `Dockerfile`, скиллы, документация, `.env.example` | распаковать, положить свой `.env`, `docker compose up -d --build` |
| `cards.tar.gz` | всё содержимое `books/` из репозитория: `cards.jsonl.gz` каждой книги, `meta.json`, профили нарезки, отчёты о качестве | распаковать в корень; `upload_projection.py` + `upload_corpus.py`, либо `reupload_all.py` разом |
| `corpus/sources.json`, `corpus/*.jsonl.gz` | выгрузка сервиса по API: источники и чанки со сносками, по файлу на источник | `upload_corpus.py` — эмбеддинги он считает сам |
| `<имя>.dump` | снятый на хосте `pg_dump` (кладётся флагом `--include-dump`) | `pg_restore` в чистую базу |
| `MANIFEST.txt`, `SHA256SUMS` | состав набора, счётчики, контрольные суммы | — |

Состав архивов берётся из `git ls-files`, а не обходом каталога: что
исключено из репозитория (`.env`, кэш растров, OCR, `.venv`), исключено и
из бэкапа — одним правилом на оба места. Секретов в наборе нет.

**Векторов в выгрузке по API нет.** `ChunkRead` эмбеддинги не отдаёт, и
восстановление из `corpus/` вернёт текст, иерархию и сноски, но векторы
придётся считать заново — это деньги и часы. Копия вместе с векторами
получается только через `pg_dump`; поэтому его и стоит снимать на хосте и
класть в тот же набор.

## Как снять

Полный набор, вместе с выгрузкой сервиса:

```bash
python3 scripts/backup.py --out ~/backups \
    --service-url https://<домен> --env-file ~/.corpus.env
```

Без `--service-url` собираются только `system.tar.gz` и `cards.tar.gz` —
это можно делать где угодно, где есть клон репозитория; выгрузка корпуса
требует `API_TOKEN` в файле с ключами.

Дамп базы снимается на хосте, где живёт сервис, и приобщается к набору:

```bash
docker compose exec -T db pg_dump -U corpus -Fc corpus > ~/corpus-$(date +%F).dump
python3 scripts/backup.py --out ~/backups --include-dump ~/corpus-$(date +%F).dump \
    --service-url https://<домен> --env-file ~/.corpus.env
```

Если на пути к хранилищу стоит предел на размер файла (вложение в
переписке, почта), карточки делятся на части:

```bash
python3 scripts/backup.py --out ~/backups --split-mb 25
```

Часть — самостоятельный архив со своим набором книг, а не кусок файла:
`cards-part2.tar.gz` распаковывается сам по себе, и потеря одной части не
портит остальные. У Диска такого предела нет, и по умолчанию деления нет
тоже.

## Как отправить на Google Диск

```bash
python3 scripts/upload_to_drive.py --folder-id <id папки> \
    --env-file ~/.corpus.env ~/backups/comparative-civil-law-<дата>
```

Идентификатор папки виден в её адресе:
`drive.google.com/drive/folders/<id>`. Файл льётся возобновляемой сессией
кусками по 8 МБ — обрыв на сороковом мегабайте продолжается с места
обрыва. Одноимённый файл в папке обновляется новой версией, ссылка на него
не меняется; `--keep-both` кладёт рядом второй, `--skip-existing` не
трогает вовсе.

### Ключи

Годится любой из трёх наборов в `~/.corpus.env`, скрипт берёт первый
найденный.

**1. Разовый токен — быстрее всего, живёт час.** На
[developers.google.com/oauthplayground](https://developers.google.com/oauthplayground/)
выбрать scope `https://www.googleapis.com/auth/drive.file`, обменять код
на токен и положить его:

```
GOOGLE_OAUTH_ACCESS_TOKEN=ya29.…
```

**2. Refresh-токен — для регулярного бэкапа.** OAuth-клиент типа
«Desktop app» в Google Cloud Console, один раз получить refresh-токен (тот
же Playground, галочка «Use your own OAuth credentials»):

```
GOOGLE_OAUTH_CLIENT_ID=….apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=…
GOOGLE_OAUTH_REFRESH_TOKEN=1//…
```

**3. Сервисный аккаунт — когда бэкап ходит по расписанию без человека.**
Ключ в JSON, а папку на Диске надо отдать в доступ на адрес аккаунта вида
`…@….iam.gserviceaccount.com`: своего места на Диске у него нет, и
заливка в чужую папку без явного доступа падает с 404, а не с 403.

```
GOOGLE_SERVICE_ACCOUNT_FILE=/root/.google-backup.json
```

Scope везде `drive.file` — он даёт доступ только к тому, что создано этим
же клиентом, и не открывает остальной Диск.

## По расписанию

Раз в неделю на хосте сервиса, `crontab -e`:

```cron
0 4 * * 1 cd /opt/comparative-civil-law && \
  docker compose exec -T db pg_dump -U corpus -Fc corpus > /tmp/corpus.dump && \
  python3 scripts/backup.py --out /var/backups --include-dump /tmp/corpus.dump \
    --service-url https://<домен> --env-file /root/.corpus.env && \
  python3 scripts/upload_to_drive.py --folder-id <id> --env-file /root/.corpus.env \
    /var/backups/comparative-civil-law-$(date +\%F) >> /var/log/corpus-backup.log 2>&1
```

Раз в квартал бэкап стоит проверять восстановлением: `pg_restore` в пустую
базу и сверка числа чанков с `MANIFEST.txt`. Непроверенный бэкап — это не
бэкап.
