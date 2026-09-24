#!/usr/bin/env bash
# Dump the database, then prove the dump restores. A backup nobody has
# restored is not a backup, so verification is not a separate script you can
# forget to run -- this exits non-zero if the dump cannot be read back.
#
# Usage:  scripts/backup.sh [outdir]        (default: ./backups)
# Cron:   0 4 * * *  cd /path/to/repo && scripts/backup.sh /mnt/offsite
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-backups}"
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M%S)
FILE="$OUT/gym-$STAMP.sql.gz"
PSQL=(docker compose exec -T db psql -U gym -qtA)

docker compose exec -T db pg_dump -U gym -d gym | gzip > "$FILE"
echo "dump: $FILE ($(du -h "$FILE" | cut -f1))"

# Restore into a throwaway database and compare. This is the whole point:
# without it, a dump of an empty or half-written database looks like success.
VERIFY="verify_${STAMP//-/_}"   # database names cannot contain hyphens
cleanup() { "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS $VERIFY;" >/dev/null 2>&1 || true; }
trap cleanup EXIT

"${PSQL[@]}" -d postgres -c "CREATE DATABASE $VERIFY;" >/dev/null
gunzip -c "$FILE" | docker compose exec -T db psql -U gym -q -d "$VERIFY" >/dev/null

live=$("${PSQL[@]}" -d gym     -c "SELECT count(*) FROM occupancy;")
back=$("${PSQL[@]}" -d "$VERIFY" -c "SELECT count(*) FROM occupancy;")
newest=$("${PSQL[@]}" -d "$VERIFY" -c "SELECT max(ts) FROM occupancy;")

if [ "$live" != "$back" ]; then
  echo "RESTORE FAILED: live has $live rows, restored copy has $back" >&2
  exit 1
fi
echo "verified: $back rows restored, newest $newest"

# ponytail: keep the last 14 dumps. Daily dumps of a table this size are a few
# MB each; add real retention when that stops being true.
ls -1t "$OUT"/gym-*.sql.gz | tail -n +15 | xargs -r rm --
