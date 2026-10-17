# Runbook del piloto MinIO -> Garage (bucket `research`)

Runbook operativo del piloto de migracion. La estrategia y el por que estan en
[OBJECT_STORAGE_MIGRATION.md](OBJECT_STORAGE_MIGRATION.md); la copia la hace
`data-engine/scripts/storage/migrate_minio_to_garage.py`. Este documento solo
describe pasos: no ejecuta nada por si solo. Coste: 0 EUR (Garage es AGPL y
convive con MinIO en la misma VM).

## Principios (no negociables)

- **MinIO sigue vivo en todo el piloto.** No se para, no se borra, no se
  retira. Es la copia de seguridad del corte.
- **Nada se borra.** Ni en MinIO ni en Garage, en ningun paso, incluido el
  rollback.
- **Toda copia va verificada con sha256**: el script relee cada objeto en
  destino y lo compara con el origen. Un paso con errores no se da por hecho.
- **Los hashes e informes se conservan** (`--report`): son la evidencia de que
  el piloto fue fiel, y hay que re-medirlos antes del corte (las cifras de
  abajo son una foto del inicio, no un estado garantizado).

## Inventario de partida (foto del inicio del piloto)

- Bucket `research`: **5.200 objetos, 2,83 GB**.
- Son cifras del momento del inventario, no un contrato: la copia inicial con
  `--dry-run` y su informe dan la foto real en cada ejecucion, y el delta del
  paso 3 cierra cualquier diferencia.

## Paso 1 - Copia inicial idempotente (sin activar el endpoint)

La app sigue apuntando a MinIO: las `OBJECT_STORAGE_*` de `.env.production`
siguen comentadas. Garage aun no recibe trafico de la aplicacion.

```bash
# Primero en seco: no escribe nada, solo informa.
docker compose -f docker-compose.prod.yml exec \
  -e SRC_ACCESS_KEY=$MINIO_ROOT_USER -e SRC_SECRET_KEY=$MINIO_ROOT_PASSWORD \
  -e DST_ACCESS_KEY=$GARAGE_ACCESS_KEY -e DST_SECRET_KEY=$GARAGE_SECRET_KEY backend \
  python -m scripts.storage.migrate_minio_to_garage \
    --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \
    --bucket research --dry-run --report /tmp/migracion-dryrun.json

# Copia real. Idempotente: se puede repetir hasta que el informe salga limpio.
docker compose -f docker-compose.prod.yml exec \
  -e SRC_ACCESS_KEY=$MINIO_ROOT_USER -e SRC_SECRET_KEY=$MINIO_ROOT_PASSWORD \
  -e DST_ACCESS_KEY=$GARAGE_ACCESS_KEY -e DST_SECRET_KEY=$GARAGE_SECRET_KEY backend \
  python -m scripts.storage.migrate_minio_to_garage \
    --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \
    --bucket research --report /tmp/migracion-inicial.json
```

Cada objeto copiado se relee de Garage y se compara sha256 con MinIO. Codigo de
salida distinto de 0 = algo falta, difiere o no se puede leer: no seguir.

## Paso 2 - Ventana de mantenimiento: parada total de productores

Todo servicio que puede escribir en storage se para, para que no queden bytes
nuevos solo en MinIO con la base apuntando a Garage:

```bash
docker compose -p cavaai -f docker-compose.prod.yml stop \
  backend worker worker-thesis worker-kpis worker-knowledge \
  worker-alerts worker-gdelt scheduler
```

Postgres, Redis, Qdrant, MinIO y Garage siguen arriba; la app no responde hasta
el paso 4. Confirmar con `docker compose -p cavaai -f docker-compose.prod.yml ps`
que solo quedan los servicios de datos.

> **`worker-knowledge` estaba omitido en la lista original del piloto.** No
> monta `MINIO_*` (su configuracion por defecto cae a un `localhost` no
> contactable, asi que no puede escribir en el storage de objetos), pero se
> incluye en la parada: durante la ventana su dependencia `backend` esta
> parada de todos modos, y pararlo cuesta cero y quita la duda. La lista de
> la fase 3 de OBJECT_STORAGE_MIGRATION.md queda corregida en este mismo PR.

## Paso 3 - Delta, verify-only y cambio de endpoint

Con los productores parados, el backend ya no sirve `exec`: se usa `run`.

```bash
# Delta: lo escrito en MinIO desde la copia inicial.
docker compose -p cavaai -f docker-compose.prod.yml run --rm --no-deps \
  -e SRC_ACCESS_KEY=$MINIO_ROOT_USER -e SRC_SECRET_KEY=$MINIO_ROOT_PASSWORD \
  -e DST_ACCESS_KEY=$GARAGE_ACCESS_KEY -e DST_SECRET_KEY=$GARAGE_SECRET_KEY backend \
  python -m scripts.storage.migrate_minio_to_garage \
    --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \
    --bucket research --report /tmp/migracion-delta.json

# Verificacion final: tiene que dar ok=true, 0 faltantes, 0 diferencias, salida 0.
docker compose -p cavaai -f docker-compose.prod.yml run --rm --no-deps \
  -e SRC_ACCESS_KEY=$MINIO_ROOT_USER -e SRC_SECRET_KEY=$MINIO_ROOT_PASSWORD \
  -e DST_ACCESS_KEY=$GARAGE_ACCESS_KEY -e DST_SECRET_KEY=$GARAGE_SECRET_KEY backend \
  python -m scripts.storage.migrate_minio_to_garage \
    --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \
    --bucket research --verify-only --report /tmp/migracion-verify.json
```

- Si `--verify-only` **no** sale con 0 errores: no continuar. Levantar los
  servicios tal cual (siguen en MinIO, no se ha tocado `.env.production`) y
  revisar el informe.
- Si sale limpio: descomentar `OBJECT_STORAGE_ENDPOINT` / `OBJECT_STORAGE_ACCESS_KEY` /
  `OBJECT_STORAGE_SECRET_KEY` / `OBJECT_STORAGE_REGION` en `.env.production`
  apuntando a Garage y recrear:

```bash
docker compose -p cavaai -f docker-compose.prod.yml up -d --no-deps \
  backend worker worker-thesis worker-kpis worker-knowledge \
  worker-alerts worker-gdelt scheduler
```

Verificar `/health/ready` (sonda `minio` = ok; el nombre de la sonda es
historico, el backend habla S3 contra Garage).

## Paso 4 - Prueba funcional y backup desde Garage

1. **Tenant QA**: subir y leer un documento con la cuenta de pruebas
   ("Instinct Audit", marcada como test; nunca con tenants reales). Confirmar
   que el objeto aparece en Garage y no en MinIO.
2. **Backup contra Garage** con el versionado desactivado (Garage no tiene
   versionado de objetos): `--no-enable-versioning` en `backup_minio.py`, o
   `--minio-no-versioning` en `backup_all.py`, y nunca `--include-versions`.
   El manifiesto lo declara como "no gestionado". Hasta la fase de cierre, el
   campo `server_release` del manifiesto seguira diciendo MinIO: es conocido.

## Paso 5 - Rollback (si algo falla tras el corte)

1. **Primero la copia inversa verificada**: lo escrito en Garage desde el
   corte se copia de vuelta a MinIO con el mismo script, origen y destino
   invertidos, y se exige el mismo resultado (`--verify-only` con 0 errores)
   **antes** de devolver el endpoint.
2. Comentar de nuevo las `OBJECT_STORAGE_*` en `.env.production` y repetir la
   parada total y recreacion del paso 2/3: la app vuelve a MinIO, que nunca
   se dejo de escribir como copia intacta.
3. No se borra nada en Garage: queda como estaba para diagnosticar.

## Criterio de salida del piloto

- **>= 7 dias estables** en produccion sobre Garage (sin errores de storage en
  backend ni workers, backups diarios correctos).
- **Restore probado** desde un backup hecho contra Garage (taladro de
  restauracion como el de 2026-09-26, conteos contra el manifiesto).
- Solo entonces se plantea retirar MinIO, en un PR aparte (fase 5 de
  OBJECT_STORAGE_MIGRATION.md). El volumen `cavaai-prod-minio` no se borra en
  ese mismo paso.
