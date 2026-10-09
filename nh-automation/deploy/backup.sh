#!/bin/sh
# Nightly backup (P0-5): pg_dump to $BACKUP_DIR, gzip'd, then prune dumps
# older than $BACKUP_RETENTION_DAYS. Also runnable manually for an on-demand
# backup: docker compose -f deploy/docker-compose.prod.yml exec backup /usr/local/bin/backup.sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[backup] $(date -Is) starting dump of ${POSTGRES_DB} -> ${FILE}"

PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
  -h "${POSTGRES_HOST:-db}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --format=plain \
  | gzip > "${FILE}"

echo "[backup] $(date -Is) done: $(du -h "${FILE}" | cut -f1)"

echo "[backup] pruning dumps older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete
