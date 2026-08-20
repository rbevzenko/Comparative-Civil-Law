#!/usr/bin/env bash
# Недельный бэкап одной командой: дамп базы, сборка набора, заливка на Диск.
#
#     scripts/weekly_backup.sh
#
# Придумано для крона: в расписании должна стоять ОДНА строка, а не связка
# из трёх команд через && — иначе первая же ошибка посреди связки оставляет
# после себя недособранный набор, и понять это можно только по молчанию.
#
# Настройки берутся из окружения, разумные значения подставляются сами:
#
#     BACKUP_OUT=/root/backups   куда складывать наборы
#     BACKUP_KEEP=2              сколько наборов держать на сервере
#     BACKUP_FOLDER="Comparative Civil Law Backups"   папка на Диске
#     SERVICE_URL=https://…      адрес сервиса; иначе берётся MCP_DOMAIN из .env
#
# Секреты (API_TOKEN сервиса, ключ Google) читаются скриптами из `.env` в
# корне репозитория и в командную строку не попадают.

set -euo pipefail
# Крон запускается с урезанным PATH, docker в нём обычно не находится.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

cd "$(dirname "$(readlink -f "$0")")/.."
REPO="$PWD"
[ -f .env ] || { echo "нет .env в $REPO"; exit 1; }

OUT="${BACKUP_OUT:-/root/backups}"
KEEP="${BACKUP_KEEP:-2}"
FOLDER="${BACKUP_FOLDER:-Comparative Civil Law Backups}"
DAY="$(date +%F)"
SET="$OUT/comparative-civil-law-$DAY"
DUMP="$OUT/corpus-$DAY.dump"

# Адрес сервиса и имена базы — из .env, чтобы не держать их в двух местах.
# grep, а не source: в .env есть значения с пробелами и знаками доллара,
# и выполнять этот файл как код незачем.
env_get() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | tr -d "\"'"; }
URL="${SERVICE_URL:-https://$(env_get MCP_DOMAIN)}"
PGUSER_="$(env_get POSTGRES_USER)"; PGUSER_="${PGUSER_:-corpus}"
PGDB_="$(env_get POSTGRES_DB)"; PGDB_="${PGDB_:-corpus}"

mkdir -p "$OUT"
echo "=== $(date +'%F %T') бэкап начат, сервис $URL"

# Дамп пишется во временный файл и переименовывается только после успеха:
# оборванный pg_dump иначе останется лежать под правильным именем и будет
# выглядеть как хороший бэкап.
docker compose exec -T db pg_dump -U "$PGUSER_" -Fc "$PGDB_" > "$DUMP.part"
mv "$DUMP.part" "$DUMP"
echo "дамп базы: $(du -h "$DUMP" | cut -f1)"

python3 scripts/backup.py --out "$OUT" --include-dump "$DUMP" \
    --service-url "$URL" --env-file .env

python3 scripts/upload_to_drive.py --folder-name "$FOLDER" \
    --subfolder "comparative-civil-law-$DAY" --env-file .env "$SET"

# Дамп уже лежит внутри набора — второй копии рядом с ним не нужно.
rm -f "$DUMP"

# Чистка: на сервере держим последние $KEEP наборов. Диск на CPX22 меньше
# трёх дампов подряд, и заполнить его бэкапами — способ уронить сервис.
# Сортировка по ИМЕНИ, а не по времени: в имени стоит дата, и наборы,
# созданные в одну минуту (первый запуск и проверочный), при сортировке по
# mtime встают в произвольном порядке — можно снести свежий.
ls -1d "$OUT"/comparative-civil-law-* 2>/dev/null | sort -r | tail -n "+$((KEEP + 1))" | while read -r old; do
    echo "убираю старый набор: $old"
    rm -rf "$old"
done

echo "=== $(date +'%F %T') бэкап готов: $SET"
