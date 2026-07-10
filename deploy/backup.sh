#!/usr/bin/env bash
# Daily pg_dump of the warehouse, gzipped, with a retention window.
# Restore path (documented, and exercised once during M6):
#   gunzip -c backups/bridge-YYYY-mm-dd.sql.gz | \
#     docker compose -f docker-compose.prod.yml exec -T db psql -U bridge -d TARGET_DB
set -euo pipefail

APP_DIR=/opt/bridge
BACKUP_DIR="$APP_DIR/backups"
RETENTION_DAYS=14

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

STAMP=$(date -u +%Y-%m-%d)
OUT="$BACKUP_DIR/bridge-${STAMP}.sql.gz"

docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U bridge -d bridge | gzip > "$OUT"

echo "[backup] wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Prune backups older than the retention window.
find "$BACKUP_DIR" -name 'bridge-*.sql.gz' -mtime +"$RETENTION_DAYS" -print -delete
