#!/usr/bin/env bash
# Backup de CavaAI (produccion personal, Linux/Oracle VM).
#
# Genera backups/YYYYMMDD-HHMMSS/ con:
#   - postgres.dump      (pg_dump -Fc, canonico: research/evidence/thesis)
#   - qdrant-snapshots/  (un .snapshot por coleccion, via API de Qdrant)
#   - minio.tar.gz       (documentos crudos; volumen parado si --stop-storage)
#   - duckdb.tar.gz      (analytics local)
#   - manifest.txt       (fecha, versiones, conteos basicos)
#
# Retencion: conserva los ultimos ${BACKUP_RETENTION_COUNT:-8} backups locales
# y borra los mas antiguos al final de cada ejecucion correcta. En R2, la
# retencion la impone el lifecycle del bucket (ver docs/BACKUP_RESTORE.md).
#
# Subida opcional a Cloudflare R2 (free tier 10 GB) con rclone:
#   RCLONE_REMOTE=r2:cavaai-backups ./scripts/backup.sh
#
# Uso:
#   ./scripts/backup.sh [--stop-storage]
set -euo pipefail

COMPOSE="${COMPOSE_CMD:-docker compose -f docker-compose.prod.yml}"
# Knobs para el drill de verificacion en proyecto aislado (ver
# scripts/verify-backup-restore.sh); en produccion no hace falta definirlos.
QDRANT_API_URL="${QDRANT_API_URL:-http://127.0.0.1:6333}"
QDRANT_VOLUME="${QDRANT_VOLUME:-cavaai-prod-qdrant}"
MINIO_VOLUME="${MINIO_VOLUME:-cavaai-prod-minio}"
DUCKDB_VOLUME="${DUCKDB_VOLUME:-cavaai-prod-duckdb}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="backups/${STAMP}"
STOP_STORAGE=0
[ "${1:-}" = "--stop-storage" ] && STOP_STORAGE=1

mkdir -p "${DEST}"
echo "[backup] destino: ${DEST}"

# 1) Postgres: dump consistente en caliente (formato custom comprimido).
echo "[backup] postgres…"
${COMPOSE} exec -T postgres pg_dump -U "${POSTGRES_USER:-portfolio}" -Fc "${POSTGRES_DB:-cavaai_research}" > "${DEST}/postgres.dump"

# 2) Qdrant: snapshot POR COLECCION via API (puerto solo-loopback del compose).
#    Los snapshots por coleccion se restauran con la API de upload sin tocar el
#    volumen; un snapshot full-storage exigiria copiar el fichero dentro del
#    volumen a mano y por eso se evita.
echo "[backup] qdrant…"
if COLLECTIONS_JSON=$(curl -fsS "${QDRANT_API_URL}/collections"); then
  mapfile -t QDRANT_COLLECTIONS < <(printf '%s' "${COLLECTIONS_JSON}" | python3 -c 'import json,sys; [print(c["name"]) for c in json.load(sys.stdin)["result"]["collections"]]')
  mkdir -p "${DEST}/qdrant-snapshots"
  for COLL in "${QDRANT_COLLECTIONS[@]}"; do
    echo "[backup] qdrant: snapshot de ${COLL}…"
    SNAP_NAME=$(curl -fsS -X POST "${QDRANT_API_URL}/collections/${COLL}/snapshots" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')
    curl -fsS "${QDRANT_API_URL}/collections/${COLL}/snapshots/${SNAP_NAME}" -o "${DEST}/qdrant-snapshots/${COLL}.snapshot"
  done
else
  echo "[backup] aviso: API de qdrant no disponible; se copiara el volumen en crudo"
  docker run --rm -v "${QDRANT_VOLUME}":/data:ro -v "$(pwd)/${DEST}":/out alpine tar czf /out/qdrant-raw.tar.gz -C /data .
fi

if [ "${STOP_STORAGE}" = "1" ]; then
  echo "[backup] parando minio y backend para snapshot consistente de volumenes…"
  ${COMPOSE} stop backend worker scheduler minio
fi

# 3) MinIO: tar del volumen (datos en reposo, consistencia garantizada si parado).
echo "[backup] minio…"
docker run --rm -v "${MINIO_VOLUME}":/data:ro -v "$(pwd)/${DEST}":/out alpine tar czf /out/minio.tar.gz -C /data .

# 4) DuckDB: fichero unico.
echo "[backup] duckdb…"
docker run --rm -v "${DUCKDB_VOLUME}":/data:ro -v "$(pwd)/${DEST}":/out alpine sh -c 'cd /data && tar czf /out/duckdb.tar.gz . || true'

if [ "${STOP_STORAGE}" = "1" ]; then
  ${COMPOSE} start minio backend worker scheduler
fi

# 5) Manifest.
{
  echo "timestamp_utc=${STAMP}"
  echo "postgres_db=${POSTGRES_DB:-cavaai_research}"
  echo "git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo n/a)"
  echo "files:"
  ls -lh "${DEST}"
} > "${DEST}/manifest.txt"

echo "[backup] completado: ${DEST}"

# 6) Subida opcional a R2 (rclone config previamente: rclone config → S3-compatible).
if [ -n "${RCLONE_REMOTE:-}" ]; then
  echo "[backup] subiendo a ${RCLONE_REMOTE}…"
  rclone copy "${DEST}" "${RCLONE_REMOTE}/${STAMP}" --transfers 4
  echo "[backup] subida completada"
fi

# 7) Retencion local: conserva los N mas recientes, borra el resto.
# Solo tras ejecucion correcta (set -e: si algo fallo, no se llega aqui).
RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-8}"
if [ "${RETENTION_COUNT}" -ge 1 ] 2>/dev/null; then
  mapfile -t OLD_DIRS < <(ls -1d backups/*/ 2>/dev/null | sort | head -n "-${RETENTION_COUNT}") || true
  if [ "${#OLD_DIRS[@]}" -gt 0 ]; then
    echo "[backup] retencion: borrando ${#OLD_DIRS[@]} backup(s) antiguos (conservo ${RETENTION_COUNT})…"
    printf '%s\n' "${OLD_DIRS[@]}"
    rm -rf "${OLD_DIRS[@]}"
  fi
fi
