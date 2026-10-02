#!/usr/bin/env bash
# Backup cifrado de MongoDB Atlas (sesiones de Better Auth) a coste 0 EUR.
#
# Atlas Free/M0 NO incluye backups (docs oficiales:
# https://www.mongodb.com/docs/atlas/backup-restore-cluster/), asi que se usa
# mongodump. Este script SOLO LEE de Atlas. Nunca restaura.
#
# Requisitos: mongodump (database-tools) y age. Variables:
#   MONGODB_URI          URI de Atlas (no se imprime nunca)
#   AGE_RECIPIENT        clave PUBLICA age (age1...). La privada la guarda solo Nico
#   BACKUP_DIR           por defecto ./backups-mongo
#   BACKUP_RETENTION_COUNT  por defecto 8
#   RCLONE_REMOTE        opcional, p. ej. r2:cavaai-backups (free tier R2)
#
# Uso: MONGODB_URI=... AGE_RECIPIENT=age1... ./scripts/mongo-backup.sh
set -euo pipefail
umask 077

: "${MONGODB_URI:?falta MONGODB_URI}"
: "${AGE_RECIPIENT:?falta AGE_RECIPIENT (clave publica age)}"
case "${AGE_RECIPIENT}" in age1*) ;; *) echo "[mongo-backup] AGE_RECIPIENT debe ser una clave publica age1..." >&2; exit 2 ;; esac
command -v mongodump >/dev/null || { echo "[mongo-backup] falta mongodump" >&2; exit 2; }
command -v age >/dev/null || { echo "[mongo-backup] falta age" >&2; exit 2; }

BACKUP_DIR="${BACKUP_DIR:-backups-mongo}"
KEEP="${BACKUP_RETENTION_COUNT:-8}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/mongo-${STAMP}.archive.gz.age"
mkdir -p "${BACKUP_DIR}"
trap 'rm -f "${OUT}.tmp"' EXIT

echo "[mongo-backup] volcando a ${OUT} (cifrado, sin fichero en claro)…"
# La URI va por fichero de config efimero (process substitution): no aparece
# en `ps` ni en logs.
mongodump --config <(printf 'uri: "%s"\n' "${MONGODB_URI}") --archive --gzip | age -r "${AGE_RECIPIENT}" -o "${OUT}.tmp"
mv "${OUT}.tmp" "${OUT}"
sha256sum "${OUT}" > "${OUT}.sha256"
echo "[mongo-backup] ok: $(wc -c < "${OUT}") bytes"

if [ -n "${RCLONE_REMOTE:-}" ]; then
  rclone copy "${OUT}" "${RCLONE_REMOTE}/mongo/" && rclone copy "${OUT}.sha256" "${RCLONE_REMOTE}/mongo/"
  echo "[mongo-backup] subido a ${RCLONE_REMOTE}/mongo/"
fi

# Retencion local: conserva los ultimos KEEP.
ls -1t "${BACKUP_DIR}"/mongo-*.archive.gz.age 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r OLD; do
  rm -f "${OLD}" "${OLD}.sha256"
done
