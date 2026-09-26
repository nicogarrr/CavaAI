#!/usr/bin/env bash
# Drill de verificacion de backup/restore para la VM de produccion.
#
# NO toca contenedores ni volumenes de produccion: genera una copia del
# compose de prod con nombres/puertos propios (cavaai-verify-*), restaura
# ahi un backup real con el MISMO scripts/restore.sh y verifica Postgres,
# Qdrant, MinIO y DuckDB. Al terminar (bien o mal) baja el proyecto y borra
# sus volumenes.
#
# Prerequisitos en la VM: docker compose v2, curl, python3, y un backup
# generado por scripts/backup.sh. El .env de produccion se reutiliza (las
# credenciales internas son las mismas; los servicios van en una red propia).
#
# Uso: ./scripts/verify-backup-restore.sh backups/YYYYMMDD-HHMMSS
set -euo pipefail

BACKUP_PATH="${1:?Uso: ./scripts/verify-backup-restore.sh backups/YYYYMMDD-HHMMSS}"
case "${BACKUP_PATH}" in backups/*) ;; *) echo "El backup debe estar dentro de ./backups/"; exit 1;; esac
[ -f "${BACKUP_PATH}/postgres.dump" ] || { echo "No existe ${BACKUP_PATH}/postgres.dump"; exit 1; }

VERIFY_COMPOSE="backups/.verify-compose.yml"
export COMPOSE_CMD="docker compose -p cavaai-verify -f ${VERIFY_COMPOSE}"
export QDRANT_API_URL="http://127.0.0.1:16333"
export QDRANT_VOLUME="cavaai-verify-qdrant"
export MINIO_VOLUME="cavaai-verify-minio"
export DUCKDB_VOLUME="cavaai-verify-duckdb"
# Sin caddy (puerto 80 es de produccion) ni worker/scheduler: no hacen falta
# para verificar datos y su arranque tocaria colas reales.
export RESTORE_UP_SERVICES="postgres redis qdrant minio backend"

cleanup() {
  echo "[verify] limpieza: bajando el proyecto aislado y borrando sus volumenes…"
  ${COMPOSE_CMD} down -v --remove-orphans >/dev/null 2>&1 || true
  docker volume rm cavaai-verify-freshduck >/dev/null 2>&1 || true
  rm -f "${VERIFY_COMPOSE}"
}
trap cleanup EXIT

# ---------------------------------------------------------------- 1/5 ----
echo "[verify] 1/5 arranque con volumen NUEVO (imagen Dockerfile.prod)…"
docker build -q -f data-engine/Dockerfile.prod -t cavaai-backend:verify data-engine >/dev/null
docker volume rm cavaai-verify-freshduck >/dev/null 2>&1 || true
docker volume create cavaai-verify-freshduck >/dev/null
# Un volumen named nuevo hereda propietario del /data de la imagen. Sin el
# chown del Dockerfile seria root-owned y este touch fallaria (USER cavaai).
docker run --rm -v cavaai-verify-freshduck:/data cavaai-backend:verify touch /data/.write-ok
echo "[verify] volumen nuevo escribible por el usuario de la app: OK"

# ---------------------------------------------------------------- 2/5 ----
echo "[verify] 2/5 proyecto compose aislado (nombres, puertos y volumenes propios)…"
# Copia del compose de prod con identidad propia. sed deterministico, sin
# depender de la semantica de merge de overrides de compose.
sed -e 's/container_name: cavaai-/container_name: cavaai-verify-/' \
    -e 's/"127.0.0.1:6333:6333"/"127.0.0.1:16333:6333"/' \
    -e 's/name: cavaai-prod-/name: cavaai-verify-/' \
    docker-compose.prod.yml > "${VERIFY_COMPOSE}"

${COMPOSE_CMD} up -d postgres redis qdrant minio
echo "[verify] esperando a Qdrant en ${QDRANT_API_URL}…"
for _ in $(seq 1 30); do
  curl -fsS "${QDRANT_API_URL}/collections" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "${QDRANT_API_URL}/collections" >/dev/null

# ---------------------------------------------------------------- 3/5 ----
echo "[verify] 3/5 restore REAL contra el proyecto aislado…"
./scripts/restore.sh "${BACKUP_PATH}" --confirm-restore

# ---------------------------------------------------------------- 4/5 ----
echo "[verify] 4/5 comprobaciones…"
PG_COUNT() { ${COMPOSE_CMD} exec -T postgres psql -U "${POSTGRES_USER:-portfolio}" -d "${POSTGRES_DB:-cavaai_research}" -tAc "$1"; }

TABLES=$(PG_COUNT "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "${TABLES}" -gt 0 ] || { echo "[verify] ERROR: postgres del drill sin tablas"; exit 1; }
echo "[verify] postgres: ${TABLES} tablas publicas. Filas por tabla (comparar con produccion):"
PG_COUNT "SELECT string_agg(format('%I', table_name), ' ' ORDER BY table_name) FROM information_schema.tables WHERE table_schema='public'" \
  | tr ' ' '\n' \
  | while read -r T; do [ -n "${T}" ] && echo "  ${T}: $(PG_COUNT "SELECT count(*) FROM \"${T}\"")"; done

QCOLLS=$(curl -fsS "${QDRANT_API_URL}/collections" | python3 -c 'import json,sys; [print(c["name"]) for c in json.load(sys.stdin)["result"]["collections"]]')
[ -n "${QCOLLS}" ] || { echo "[verify] ERROR: qdrant del drill sin colecciones"; exit 1; }
for C in ${QCOLLS}; do
  PTS=$(curl -fsS "${QDRANT_API_URL}/collections/${C}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["points_count"])')
  echo "[verify] qdrant: ${C} -> ${PTS} puntos (comparar con produccion)"
done

docker run --rm -v "${MINIO_VOLUME}":/data:ro alpine sh -c 'test -n "$(find /data -type f -print -quit)"' \
  && echo "[verify] minio: volumen con datos OK"
docker run --rm -v "${DUCKDB_VOLUME}":/data:ro alpine sh -c 'test -n "$(find /data -type f -print -quit)"' \
  && echo "[verify] duckdb: volumen con datos OK"

# ---------------------------------------------------------------- 5/5 ----
echo "[verify] 5/5 TODO OK. Comparacion final sugerida: filas/puntos de arriba contra"
echo "    produccion (psql en cavaai-postgres y http://127.0.0.1:6333/collections)."
echo "[verify] la limpieza del proyecto aislado corre sola al salir."
