#!/usr/bin/env bash
# Полный дамп базы корпуса и выгрузка его на Google Drive.
#
# Запускается НА МАШИНЕ СЕРВИСА (37-27-248-75), из каталога с
# docker-compose.yml:
#
#     ./scripts/backup_db.sh
#
# Почему здесь, а не из агента: агент ходит в сервис только по HTTP, а API
# не отдаёт эмбеддинги — 89 тысяч векторов по 1536 чисел через него не
# вытащить. Да и сам файл дампа в сотни мегабайт через API-коннектор не
# пролезет. pg_dump рядом с базой снимает всё и сразу.
#
# Разовая настройка rclone (один раз, на машине сервиса):
#     rclone config          # remote с именем gdrive, тип drive
#     rclone lsd gdrive:     # проверка
# Идентификатор папки берётся из ссылки на неё.
#
# Хранится семь последних дампов: суточного цикла хватает, а место на
# CPX22 не резиновое.

set -euo pipefail

REMOTE="${REMOTE:-gdrive}"
FOLDER_ID="${FOLDER_ID:-1coTYG9E4hN_TUaIkFZvO93q53ZnqGrW1}"
OUT_DIR="${OUT_DIR:-/var/backups/corpus}"
KEEP="${KEEP:-7}"

# Пароль и имя базы берутся из .env рядом с docker-compose.yml и в
# аргументы команды не попадают: иначе они осядут в истории оболочки и в
# списке процессов.
[ -f .env ] || { echo "нет .env рядом с docker-compose.yml" >&2; exit 1; }
set -a; . ./.env; set +a
DB_NAME="${POSTGRES_DB:-corpus}"
DB_USER="${POSTGRES_USER:-corpus}"

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%d-%H%M)"
DUMP="$OUT_DIR/corpus-$STAMP.dump.gz"

echo "== pg_dump $DB_NAME"
# -Fc — формат, восстанавливаемый pg_restore выборочно, по таблицам.
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc \
  | gzip -9 > "$DUMP"
echo "   $(du -h "$DUMP" | cut -f1)  $DUMP"

echo "== выгрузка на Drive"
rclone copy "$DUMP" "$REMOTE:" --drive-root-folder-id "$FOLDER_ID" --progress

echo "== чищу старые, оставляю $KEEP"
ls -1t "$OUT_DIR"/corpus-*.dump.gz | tail -n "+$((KEEP + 1))" | xargs -r rm -v

echo "Готово: $DUMP"
echo
echo "Восстановление:"
echo "  gunzip -c corpus-<штамп>.dump.gz | docker compose exec -T db \\"
echo "      pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists"
