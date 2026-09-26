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

# 2) Qdrant (indice vectorial). backup.sh produce una de estas dos formas:
#    - qdrant-snapshots/*.snapshot  (uno por coleccion, via API)
#    - qdrant-raw.tar.gz            (copia del volumen, si la API no respondio)
#    Sin este paso el restore terminaba sin error y sin indice vectorial: el
#    RAG de los tenants volvia vacio.
#
#    El restore por snapshots usa SOLO la API de Qdrant (upload por coleccion,
#    puerto solo-loopback): nada de montar el volumen, asi que qdrant debe
#    estar ARRIBA. El intento anterior montaba el volumen :ro y luego hacia
#    rm/mkdir/cp dentro: imposible, el paso moria siempre.
if [ -d "${BACKUP_PATH}/qdrant-snapshots" ]; then
  echo "[restore] qdrant (snapshots por API)…"
  shopt -s nullglob
  QDRANT_SNAPS=("${BACKUP_PATH}"/qdrant-snapshots/*.snapshot)
  if [ "${#QDRANT_SNAPS[@]}" -eq 0 ]; then
    echo "[restore] AVISO: qdrant-snapshots/ esta vacio; el indice vectorial quedara vacio"
  fi
  for SNAP in "${QDRANT_SNAPS[@]}"; do
    COLL="$(basename "${SNAP}" .snapshot)"
    echo "[restore] qdrant: recuperando coleccion ${COLL}…"
    # Restore destructivo (ya confirmado con --confirm-restore): la coleccion
    # se borra y se recrea desde el snapshot.
    curl -fsS -X DELETE "http://127.0.0.1:6333/collections/${COLL}" -o /dev/null || true
    curl -fsS -X PUT "http://127.0.0.1:6333/collections/${COLL}/snapshots/upload?priority=snapshot" \
      -H "Content-Type: multipart/form-data" -F "snapshot=@${SNAP}" -o /dev/null
  done
elif [ -f "${BACKUP_PATH}/qdrant-raw.tar.gz" ]; then
  echo "[restore] qdrant (volumen en crudo)…"
  ${COMPOSE} stop qdrant
  docker run --rm -v cavaai-prod-qdrant:/data -v "$(pwd)/${BACKUP_PATH}":/in:ro alpine sh -c 'rm -rf /data/* && tar xzf /in/qdrant-raw.tar.gz -C /data'
  ${COMPOSE} start qdrant
else
  echo "[restore] AVISO: el backup no contiene qdrant; el indice vectorial quedara vacio"
fi

# 3) MinIO.
if [ -f "${BACKUP_PATH}/minio.tar.gz" ]; then
  echo "[restore] minio…"
  docker run --rm -v cavaai-prod-minio:/data -v "$(pwd)/${BACKUP_PATH}":/in:ro alpine sh -c 'rm -rf /data/* && tar xzf /in/minio.tar.gz -C /data'
fi

# 4) DuckDB.
if [ -f "${BACKUP_PATH}/duckdb.tar.gz" ]; then
  echo "[restore] duckdb…"
  docker run --rm -v cavaai-prod-duckdb:/data -v "$(pwd)/${BACKUP_PATH}":/in:ro alpine sh -c 'rm -rf /data/* && tar xzf /in/duckdb.tar.gz -C /data'
fi

echo "[restore] arrancando servicios…"
${COMPOSE} up -d
echo "[restore] aplicando migraciones por si el backup es de otra version…"
${COMPOSE} exec -T backend python -m alembic upgrade head
# El compose de produccion no publica el puerto del backend, asi que el
# healthcheck va por Caddy.
echo "[restore] listo. Verifica: curl -fsS https://${BACKEND_DOMAIN:-localhost}/health/ready"
