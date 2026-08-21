#!/usr/bin/env bash
# Ночная резервная копия корпуса на Google Drive.
#
# Запускается НА МАШИНЕ СЕРВИСА (37-27-248-75), из каталога с
# docker-compose.yml:
#
#     ./scripts/backup_db.sh
#
# Отвозит на Drive три вещи:
#   corpus-<штамп>.dump.gz        полный дамп базы ВМЕСТЕ С ВЕКТОРАМИ
#   service-code-<штамп>.tar.gz   код сервиса и пайплайна, без секретов
#   repo-<штамп>.bundle           весь репозиторий с историей, одним файлом
#
# Почему это делает сервер, а не агент. Агент ходит в сервис только по HTTP,
# а API не отдаёт эмбеддинги — 89 тысяч векторов по 1536 чисел через него не
# вытащить. И сам дамп в сотни мегабайт через коннектор не пролезет: там
# файл идёт через переписку. pg_dump рядом с базой снимает всё и сразу.
#
# Разовая настройка rclone (один раз, на машине сервиса):
#     rclone config          # remote с именем gdrive, тип drive
#     rclone lsd gdrive:     # проверка
# Идентификатор папки берётся из ссылки на неё.
#
# Хранится семь последних копий: суточного цикла хватает, а место на
# CPX22 не резиновое.

set -euo pipefail

REMOTE="${REMOTE:-gdrive}"
FOLDER_ID="${FOLDER_ID:-1coTYG9E4hN_TUaIkFZvO93q53ZnqGrW1}"
OUT_DIR="${OUT_DIR:-/var/backups/corpus}"
KEEP="${KEEP:-7}"

# Пароль и имя базы берутся из .env рядом с docker-compose.yml и в аргументы
# команды не попадают: иначе они осядут в истории оболочки и в списке
# процессов. Сам .env на Drive не уезжает НИКОГДА — папка расшарена ссылкой.
[ -f .env ] || { echo "нет .env рядом с docker-compose.yml" >&2; exit 1; }
set -a; . ./.env; set +a
DB_NAME="${POSTGRES_DB:-corpus}"
DB_USER="${POSTGRES_USER:-corpus}"

command -v rclone >/dev/null || { echo "rclone не установлен: см. rclone config" >&2; exit 1; }

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%d-%H%M)"
DUMP="$OUT_DIR/corpus-$STAMP.dump.gz"
CODE="$OUT_DIR/service-code-$STAMP.tar.gz"
BUNDLE="$OUT_DIR/repo-$STAMP.bundle"

echo "== дамп базы $DB_NAME"
# -Fc — формат, из которого pg_restore достаёт и всё сразу, и отдельные таблицы.
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc \
  | gzip -9 > "$DUMP"
echo "   $(du -h "$DUMP" | cut -f1)"

echo "== код сервиса и пайплайна"
# .env исключён намеренно. .env.example остаётся: в нём имена всех
# переменных и объяснение, чем каждую заполнить, но не значения.
tar --exclude='.env' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='books' \
    -czf "$CODE" . 2>/dev/null || true
echo "   $(du -h "$CODE" | cut -f1)"

echo "== репозиторий с историей"
# Один файл, из которого клонируется всё: git clone repo-<штамп>.bundle
if [ -d .git ]; then
    git bundle create "$BUNDLE" --all
    echo "   $(du -h "$BUNDLE" | cut -f1)"
else
    echo "   .git нет, пропускаю"
    BUNDLE=""
fi

echo "== выгрузка на Drive"
for f in "$DUMP" "$CODE" $BUNDLE; do
    [ -f "$f" ] || continue
    rclone copy "$f" "$REMOTE:" --drive-root-folder-id "$FOLDER_ID"
    echo "   отправлен $(basename "$f")"
done

echo "== чищу старые, оставляю $KEEP каждого вида"
for pat in 'corpus-*.dump.gz' 'service-code-*.tar.gz' 'repo-*.bundle'; do
    # shellcheck disable=SC2012
    ls -1t "$OUT_DIR"/$pat 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -v
done

echo
echo "Готово. Восстановление:"
echo "  база:        gunzip -c corpus-<штамп>.dump.gz | docker compose exec -T db \\"
echo "                   pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists"
echo "  репозиторий: git clone repo-<штамп>.bundle corpus && cd corpus"
echo "  затем:       cp .env.example .env && \$EDITOR .env && docker compose up -d --build"
