#!/usr/bin/env bash
# Restore de CavaAI (produccion personal). DESTRUCTIVO: sobrescribe Postgres
# y los volumenes de MinIO/DuckDB. Solo en ventana de mantenimiento.
#
# Uso: ./scripts/restore.sh backups/YYYYMMDD-HHMMSS --confirm-restore
set -euo pipefail

BACKUP_PATH="${1:?Uso: ./scripts/restore.sh <backup-path> --confirm-restore}"
[ "${2:-}" = "--confirm-restore" ] || { echo "Falta --confirm-restore (operacion destructiva)"; exit 1; }
case "${BACKUP_PATH}" in backups/*) ;; *) echo "El backup debe estar dentro de ./backups/"; exit 1;; esac
[ -f "${BACKUP_PATH}/postgres.dump" ] || { echo "No existe ${BACKUP_PATH}/postgres.dump"; exit 1; }

COMPOSE="docker compose -f docker-compose.prod.yml"
echo "[restore] desde: ${BACKUP_PATH}"
echo "[restore] parando servicios…"
${COMPOSE} stop backend worker scheduler minio

# 1) Postgres: drop + restore.
echo "[restore] postgres…"
${COMPOSE} exec -T postgres dropdb -U "${POSTGRES_USER:-portfolio}" --if-exists "${POSTGRES_DB:-cavaai_research}"
${COMPOSE} exec -T postgres createdb -U "${POSTGRES_USER:-portfolio}" "${POSTGRES_DB:-cavaai_research}"
${COMPOSE} exec -T postgres pg_restore -U "${POSTGRES_USER:-portfolio}" -d "${POSTGRES_DB:-cavaai_research}" --no-owner < "${BACKUP_PATH}/postgres.dump"

# 2) MinIO.
if [ -f "${BACKUP_PATH}/minio.tar.gz" ]; then
  echo "[restore] minio…"
  docker run --rm -v cavaai-prod-minio:/data -v "$(pwd)/${BACKUP_PATH}":/in:ro alpine sh -c 'rm -rf /data/* && tar xzf /in/minio.tar.gz -C /data'
fi

# 3) DuckDB.
if [ -f "${BACKUP_PATH}/duckdb.tar.gz" ]; then
  echo "[restore] duckdb…"
  docker run --rm -v cavaai-prod-duckdb:/data -v "$(pwd)/${BACKUP_PATH}":/in:ro alpine sh -c 'rm -rf /data/* && tar xzf /in/duckdb.tar.gz -C /data'
fi

echo "[restore] arrancando servicios…"
${COMPOSE} up -d
echo "[restore] aplicando migraciones por si el backup es de otra version…"
${COMPOSE} exec -T backend python -m alembic upgrade head
echo "[restore] listo. Verifica: curl -fsS http://localhost:8000/health/ready"
