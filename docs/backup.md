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
python3 scripts/upload_to_drive.py --folder-name "Comparative Civil Law Backups" \
    --subfolder comparative-civil-law-<дата> --env-file .env \
    /root/backups/comparative-civil-law-<дата>
```

Файл льётся возобновляемой сессией кусками по 8 МБ — обрыв на сороковом
мегабайте продолжается с места обрыва. Одноимённый файл в папке
обновляется новой версией, ссылка на него не меняется; `--keep-both`
кладёт рядом второй, `--skip-existing` не трогает вовсе.

### Про папку: почему `--folder-name`, а не `--folder-id`

Ключ для бэкапа берётся со scope `drive.file` — он даёт доступ только к
тому, что создано этим же клиентом, и не открывает остальной Диск. Обратная
сторона: заранее сделанная руками папка для такого ключа НЕ СУЩЕСТВУЕТ, и
заливка в неё по идентификатору падает с 404 «файл не найден». Поэтому
папку заводит сам скрипт (`--folder-name`), а человек может потом
перетащить её в любое место Диска — доступа к своим файлам скрипт не
теряет. `--folder-id` остаётся для ключа, открывающего весь Диск.

### Ключи

**Быстрый путь — получить токен на самом сервере:**

```bash
python3 scripts/google_refresh_token.py --env-file .env          # печатает ссылку
python3 scripts/google_refresh_token.py --env-file .env --write \
    --code 'https://developers.google.com/oauthplayground/?…code=4/0A…'
```

Первая команда печатает ссылку согласия, вторая меняет на токен адрес, на
который приземлился браузер. Адрес — в ОДИНАРНЫХ кавычках: в нём есть `&`,
и без кавычек оболочка порвёт его на куски и уведёт часть в фон. Токен он
записывает в `.env` сам — мимо буфера обмена, где длинная строка легко
копируется наполовину. Нужны только `GOOGLE_OAUTH_CLIENT_ID` и
`GOOGLE_OAUTH_CLIENT_SECRET`, уже лежащие в `.env`.

OAuth Playground делает то же самое, но ненадёжно: он выписывает код
тому клиенту, чьи ключи стояли в его настройках в момент нажатия
«Authorize APIs», и токен от клиента по умолчанию отвечает потом
`invalid_grant` без объяснений.

**Для бэкапа по расписанию — refresh-токен.** Разовый
`GOOGLE_OAUTH_ACCESS_TOKEN` живёт час и для крона не годится; сервисный
аккаунт для ЛИЧНОГО Диска не годится вовсе — своего места на Диске у него
нет, и заливка падает на квоте («Service Accounts do not have storage
quota»); он работает только с общим диском Google Workspace.

Порядок такой.

1. [console.cloud.google.com](https://console.cloud.google.com/) — создать
   проект (имя любое, например `corpus-backup`).
2. «APIs & Services» → «Library» → найти **Google Drive API** → Enable.
3. «APIs & Services» → «OAuth consent screen» → тип **External**, имя
   приложения, свой почтовый адрес в двух полях контактов. Сохранить.
4. Там же «Publishing status» → **Publish app** → In production. Шаг не
   косметический: пока приложение в статусе Testing, refresh-токен
   протухает через семь дней, и недельный бэкап отвалится ровно перед
   вторым запуском. Проверки Google для scope `drive.file` не требует —
   он не относится к чувствительным.
5. «Credentials» → «Create credentials» → «OAuth client ID» → тип **Web
   application**, в «Authorized redirect URIs» добавить
   `https://developers.google.com/oauthplayground`. Записать Client ID и
   Client secret.
6. [developers.google.com/oauthplayground](https://developers.google.com/oauthplayground/)
   → шестерёнка справа сверху → галочка «Use your own OAuth credentials» →
   вставить ID и secret.
7. В левом поле «Input your own scopes» ввести
   `https://www.googleapis.com/auth/drive.file` → «Authorize APIs» → войти
   своим аккаунтом → «Allow».
8. «Exchange authorization code for tokens» → скопировать **Refresh
   token** (начинается с `1//`).
9. Положить три строки в `.env` репозитория на сервере:

```
GOOGLE_OAUTH_CLIENT_ID=….apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=…
GOOGLE_OAUTH_REFRESH_TOKEN=1//…
```

Скрипт сам меняет refresh-токен на часовой access-токен при каждом
запуске; больше к консоли Google возвращаться не нужно.

**Разовая заливка руками** обходится без всего этого: в
[OAuth Playground](https://developers.google.com/oauthplayground/) выбрать
scope `drive.file`, обменять код на токен и положить его как
`GOOGLE_OAUTH_ACCESS_TOKEN=ya29.…`. Через час он мёртв — это нормально,
для одного прогона хватает.

## По расписанию

Всё вместе — дамп базы, сборка набора, заливка, уборка старых копий —
делает `scripts/weekly_backup.sh`. Сначала прогнать руками:

```bash
cd /root/Comparative-Civil-Law
scripts/weekly_backup.sh
```

Потом поставить в крон, `crontab -e`, — раз в неделю, в ночь на
понедельник:

```cron
0 4 * * 1 /root/Comparative-Civil-Law/scripts/weekly_backup.sh >> /var/log/corpus-backup.log 2>&1
```

На сервере скрипт держит последние два набора (`BACKUP_KEEP`), остальные
удаляет: диск CPX22 меньше трёх дампов подряд, и заполнить его бэкапами —
способ уронить сервис. На Диске не удаляется ничего.

Раз в месяц стоит заглядывать в журнал:

```bash
tail -40 /var/log/corpus-backup.log
```

Раз в квартал бэкап стоит проверять восстановлением: `pg_restore` в пустую
базу и сверка числа чанков с `MANIFEST.txt`. Непроверенный бэкап — это не
бэкап.

## Тексты, у которых второй копии не было вовсе

Тридцать один источник австрийского корпуса существовал ТОЛЬКО в базе
сервиса. Его выгрузка лежит теперь прямо в репозитории — `archive/
service-only/`, 31 912 фрагментов, — и уезжает на GitHub при каждом push.
Это независимая от бэкапа страховка: даже если пропадут и машина, и Диск,
эти тексты останутся. `archive/sources.json` рядом хранит реквизиты всех
источников, без которых архив не восстановить.

Собирается это `scripts/backup_corpus.py` — выгрузка по API в JSONL по
файлу на источник. Он проще `backup.py` и делает только одно; нужен, когда
надо освежить `archive/` в репозитории, а не собрать полный набор.
