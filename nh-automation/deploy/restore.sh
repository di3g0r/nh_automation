#!/bin/sh
# Restores a dump produced by backup.sh into the running `db` service.
#
# Usage (from the repo root, with the prod stack already up):
#   ./deploy/restore.sh deploy/backups/nh_automation_20261008_020000.sql.gz
#
# WARNING: this drops and recreates the target database. Only run it when
# you mean to replace current data (e.g. disaster recovery, or testing a
# restore as required by NFR-5).
set -eu

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 <path-to-dump.sql.gz>" >&2
  exit 1
fi

DUMP_FILE="$1"
COMPOSE_FILE="$(dirname "$0")/docker-compose.prod.yml"

if [ ! -f "${DUMP_FILE}" ]; then
  echo "Dump file not found: ${DUMP_FILE}" >&2
  exit 1
fi

# Load POSTGRES_* vars from .env at the repo root, if present.
if [ -f "$(dirname "$0")/../.env" ]; then
  set -a
  . "$(dirname "$0")/../.env"
  set +a
fi

echo "This will DROP and recreate database '${POSTGRES_DB}'. Ctrl+C within 5s to abort."
sleep 5

docker compose -f "${COMPOSE_FILE}" exec -T db dropdb -U "${POSTGRES_USER}" --if-exists "${POSTGRES_DB}"
docker compose -f "${COMPOSE_FILE}" exec -T db createdb -U "${POSTGRES_USER}" -O "${POSTGRES_USER}" "${POSTGRES_DB}"

gunzip -c "${DUMP_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Restore complete from ${DUMP_FILE}."
