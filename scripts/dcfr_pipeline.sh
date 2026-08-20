#!/usr/bin/env bash
# Стандартный прогон книги рубрики DCFR, у которой единица — ПОЛОСА.
#
#   scripts/dcfr_pipeline.sh --book <id> --pdf <файл> --pages 51-608 \
#       [--profile <файл>] [--marker-line | --keep-notes] [--sup-max 7.2] \
#       [--level '^PART\s+[IVX]+' --level '^Case\s+\d{1,2}:'] \
#       [--no-upload]
#
# Зачем. В папке DCFR полсотни книг, и полтора десятка из них — тома серии
# Common Core с одинаковой вёрсткой Cambridge: тело 10.0, сноски 8.0,
# колонтитул 9.0 с колонцифрой, знак сноски 6.5, номер сноски в аппарате
# 5.3. Повторять для каждой один и тот же десяток команд — значит рано или
# поздно забыть шаг и заметить это уже в корпусе.
#
# Порядок шагов НЕ произвольный:
#   1. pages_digital        — разбор полос по профилю
#   2. rebuild_notes        — аппарат; --marker-line, если номер сноски
#                             стоит отдельной строкой мельче её текста
#   3. fill_printed_page    — колонцифры, пропущенные на полосах без
#                             колонтитула (первая полоса главы)
#   4. inline_superscripts  — знаки сносок в текст
#   5. extract              — карточки
#   6. hierarchy            — путь по заголовкам
#   7. reflow               — сборка абзацев, СРАЗУ, до выгрузки
#   8. qa_report            — до любой выгрузки
#
# Секреты берутся из ~/.corpus.env и в аргументы не попадают.

set -euo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S=/root/.claude/skills/synced/complaw-corpus/scripts
ENVFILE="${ENVFILE:-/home/user/.corpus.env}"
BASE="${BASE:-https://37-27-248-75.sslip.io}"

BOOK=""; PDF=""; PAGES=""; PROFILE=""; MARKER=""; SUPMAX="7.2"; UPLOAD=1; NOTES=1
LEVELS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --book) BOOK="$2"; shift 2;;
    --pdf) PDF="$2"; shift 2;;
    --pages) PAGES="$2"; shift 2;;
    --profile) PROFILE="$2"; shift 2;;
    --marker-line) MARKER="--marker-line"; shift;;
    --keep-notes) NOTES=0; shift;;
    --sup-max) SUPMAX="$2"; shift 2;;
    --level) LEVELS+=(--level "$2"); shift 2;;
    --no-upload) UPLOAD=0; shift;;
    *) echo "неизвестный флаг: $1" >&2; exit 1;;
  esac
done
[ -n "$BOOK" ] && [ -n "$PDF" ] && [ -n "$PAGES" ] || { echo "нужны --book, --pdf, --pages" >&2; exit 1; }
B="$R/books/$BOOK"
[ -n "$PROFILE" ] || PROFILE="$(ls "$B"/profiles/*.yaml | head -1)"

echo "== 1/8 разбор полос"
python3 "$S/pages_digital.py" "$PDF" --book "$B" --profile "$PROFILE" --pages "$PAGES" | tail -2
# rebuild_notes переписывает поле notes ВСЕГДА, даже когда штатный разбор
# уже справился: у Vicente обычный режим затёр правильно найденные сноски,
# а у Gordley --marker-line дал ноль вместо 885, потому что номер сноски
# там стоит внутри её текста, а не отдельной строкой. Отсюда --keep-notes:
# сначала смотреть, что вышло само.
if [ "$NOTES" = "1" ]; then
  echo "== 2/8 аппарат сносок"
  python3 "$R/scripts/rebuild_notes.py" --book "$B" --max-digits 4 $MARKER | head -2
else
  echo "== 2/8 аппарат сносок: оставлен как разобран (--keep-notes)"
fi
echo "== 3/8 колонцифры"
python3 "$R/scripts/fill_printed_page.py" --book "$B" --sequential | grep -E "колонцифрой|достроено"
echo "== 4/8 знаки сносок"
python3 "$R/scripts/inline_superscripts.py" --book "$B" --size-max "$SUPMAX" | grep -E "^полос|знаков"
echo "== 5/8 карточки"
python3 "$S/extract.py" --book "$B" --profile "$PROFILE" --meta "$B/meta.json" | grep -E "Карточек"
if [ ${#LEVELS[@]} -gt 0 ]; then
  echo "== 6/8 иерархия"
  python3 "$R/scripts/hierarchy_from_headings.py" --book "$B" "${LEVELS[@]}" | grep -E "заголовков|карточек с иерархией"
fi
echo "== 7/8 сборка абзацев"
python3 "$R/scripts/reflow_card_text.py" --book "$B" | grep перебрано
echo "== 8/8 контроль качества"
python3 "$S/qa_report.py" --book "$B" > /dev/null
python3 - "$B" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1] + "/report/qa.json"))
c = d["continuity"]
print(f"  карточек {d['cards']}, непрерывность {c['share']*100:.1f}%, "
      f"пропусков {c['gaps_total']}, дублей {c['duplicates_total']}")
print(f"  покрытие {d['coverage']['share']*100:.1f}%, сносок {d['footnotes']['footnotes_total']} "
      f"(у {d['footnotes']['cards_with_footnotes_share']*100:.0f}% карточек), "
      f"без иерархии {d['hierarchy']['cards_without_hierarchy']}")
L = d["lengths"]
print(f"  длина карточки: медиана {L['median']}, минимум {L['min']}, максимум {L['max']}")
if c["duplicates_total"]:
    raise SystemExit("ДУБЛИ АДРЕСОВ — выгружать нельзя, приёмник отвергнет файл целиком")
PYEOF

if [ "$UPLOAD" = "1" ]; then
  echo "== источник"
  SID=$(python3 "$R/scripts/create_source.py" --meta "$B/meta.json" --pdf "$PDF" \
        --base-url "$BASE" --env-file "$ENVFILE" --source-type textbook | grep '^source_id:' | awk '{print $2}')
  [ -n "$SID" ] || { echo "источник не завёлся" >&2; exit 1; }
  echo "  $SID"
  python3 "$S/upload_projection.py" --book "$B" --force | grep -i выгрузка
  python3 "$R/scripts/upload_corpus.py" --upload "$B/output/upload.json" --source-id "$SID" \
      --base-url "$BASE" --env-file "$ENVFILE" | tail -1
  gzip -9 -c "$B/output/cards.jsonl" > "$B/output/cards.jsonl.gz"
  echo "$SID" > "$B/source_id.txt"
fi
echo "Готово: $BOOK"
