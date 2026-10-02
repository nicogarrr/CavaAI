#!/usr/bin/env bash
# Prueba de restauracion del backup de Mongo en un mongod LOCAL desechable.
# Nunca apunta a Atlas ni a produccion: usa un contenedor efimero en 127.0.0.1.
#
# Requiere docker y age. La clave PRIVADA (AGE_IDENTITY_FILE) la aporta Nico
# en su maquina; no vive en la VM ni en el repo.
#
# Uso: AGE_IDENTITY_FILE=~/.age/cavaai.key ./scripts/mongo-restore-drill.sh backups-mongo/mongo-XXXX.archive.gz.age
set -euo pipefail
umask 077
FILE="${1:?uso: mongo-restore-drill.sh <fichero.archive.gz.age>}"
: "${AGE_IDENTITY_FILE:?falta AGE_IDENTITY_FILE}"
NAME="cavaai-mongo-drill-$$"
cleanup() { docker rm -f "${NAME}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --rm --name "${NAME}" -p 127.0.0.1:27099:27017 mongo:7 >/dev/null
for _ in $(seq 1 30); do
  docker exec "${NAME}" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && break
  sleep 1
done
age -d -i "${AGE_IDENTITY_FILE}" "${FILE}" | docker exec -i "${NAME}" mongorestore --archive --gzip --nsInclude='*.*' >/dev/null
echo "[drill] colecciones restauradas:"
LISTING=$(docker exec "${NAME}" mongosh --quiet --eval 'db.getMongo().getDBNames().filter(n=>!["admin","local","config"].includes(n)).forEach(n=>{const d=db.getSiblingDB(n);d.getCollectionNames().forEach(c=>print(n+"."+c+": "+d.getCollection(c).countDocuments()))})')
printf '%s\n' "${LISTING}"
COUNT=$(printf '%s\n' "${LISTING}" | grep -c ': ' || true)
if [ "${COUNT}" -eq 0 ]; then
  echo "[drill] FALLO: no se restauro ninguna coleccion" >&2
  exit 1
fi
echo "[drill] ok: ${COUNT} colecciones restauradas"
