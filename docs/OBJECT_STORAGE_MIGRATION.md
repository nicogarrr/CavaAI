# Migracion de almacenamiento de objetos: MinIO -> Garage

MinIO esta archivado (abril 2026). Decision: [[cavaai-minio-garage]] (compilar MinIO ahora, migrar a Garage despues). Esto es la segunda parte. Coste: 0 EUR (Garage es AGPL, imagen `dxflrs/garage:v2.4.1`, publicada para arm64).

## Que cambia y que no

- Las URIs en BD (`minio://research/tenant-N/...`) **no se reescriben**: `minio://` es solo el nombre historico del esquema. Mismo bucket (`research`), mismas claves.
- La app usa el SDK `minio` (S3 estandar) solo para `bucket_exists`, `make_bucket` y `put_object` (`document_store.py`). Garage lo soporta; se fija `MINIO_REGION=garage` para no depender de GetBucketLocation.
- **Garage no tiene versionado de objetos.** El backup por objeto (`backup_minio.py`) activa el versionado por defecto y fallaria: con Garage usar `--no-enable-versioning` (en `backup_all.py`: `--minio-no-versioning`) y no usar `--include-versions`. El manifiesto deja constancia ("no gestionado"). La proteccion contra sobrescritura pasa a ser la inmutabilidad por clave de la app + el backup diario.
- Garage no soporta ACLs de objeto; la app no las usa.

## Fases (cada una reversible)

1. **Puente (este PR).** Deploy normal: arranca `cavaai-garage` junto a `cavaai-minio`. El backend sigue en MinIO. Requiere en `.env.production`: `GARAGE_RPC_SECRET` (`openssl rand -hex 32`), `GARAGE_ACCESS_KEY` (`GK` + `openssl rand -hex 12`), `GARAGE_SECRET_KEY` (`openssl rand -hex 32`). Garage crea solo el bucket `research` y la clave (`--single-node --default-bucket`).
   Comprobar: `docker exec cavaai-garage /garage status` y `docker exec cavaai-garage /garage bucket list`.
2. **Copia verificada** (desde el contenedor backend, que ya llega a ambos por la red de compose):
   ```
   docker compose -f docker-compose.prod.yml exec \
     -e SRC_ACCESS_KEY=$MINIO_ROOT_USER -e SRC_SECRET_KEY=$MINIO_ROOT_PASSWORD \
     -e DST_ACCESS_KEY=$GARAGE_ACCESS_KEY -e DST_SECRET_KEY=$GARAGE_SECRET_KEY backend \
     python -m scripts.storage.migrate_minio_to_garage \
       --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \
       --bucket research --report /tmp/migracion.json
   ```
   Primero con `--dry-run`. Solo lee MinIO. Relee cada objeto de Garage y compara sha256. Idempotente. Codigo de salida != 0 si algo falta, difiere o no se puede leer, tambien con `--dry-run`.
3. **Corte (con parada total de productores).** Todo servicio que monta `MINIO_*` puede escribir en storage: `backend`, `worker`, `worker-thesis`, `worker-kpis`, `worker-alerts`, `worker-gdelt` y el `scheduler` que los encola. Parar solo algunos deja bytes nuevos solo en MinIO con la base apuntando a Garage, asi que el corte se hace en ventana de mantenimiento:
   1. `docker compose -p cavaai -f docker-compose.prod.yml stop backend worker worker-thesis worker-kpis worker-alerts worker-gdelt scheduler` (la app no responde hasta el paso 5; Postgres, Redis, MinIO y Garage siguen arriba).
   2. Para el backend y confirmar que no queda ningun productor: `docker compose -p cavaai -f docker-compose.prod.yml ps` solo debe mostrar los servicios de datos. Lanzar el paso 2 (copia del delta) con `docker compose run --rm --no-deps backend ...` en vez de `exec`.
   3. `--verify-only` debe dar `ok: true` y codigo de salida 0. Si no, no continuar: arrancar los servicios sin tocar el `.env` (siguen en MinIO).
   4. En `.env.production` descomentar `OBJECT_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY/REGION`.
   5. `docker compose -p cavaai -f docker-compose.prod.yml up -d --no-deps backend worker worker-thesis worker-kpis worker-alerts worker-gdelt scheduler`. Verificar `/health/ready` (sonda `minio` = ok) y subir/leer un documento con la cuenta de pruebas.
4. **Rollback.** Comentar de nuevo las 4 variables `OBJECT_STORAGE_*` y repetir la parada total de productores y recrearlos: vuelven a MinIO, que **no se ha tocado**. Lo escrito en Garage tras el corte hay que volver a copiarlo (script con origen/destino invertidos) antes de volver.
5. **Cierre (otro PR, tras >= 7 dias estables + backup verificado desde Garage):** retirar `minio` y `docker/minio`, ajustar `backup_*`/`verify_restore` y los tests de contrato. No se borra el volumen `cavaai-prod-minio` en el mismo paso.

## Riesgos conocidos

- `scripts/backup/_kit.py`, `restore_minio.py` y `verify_restore.py` siguen declarando imagen/version de MinIO en el manifiesto; hasta la fase 5 el backup funciona contra Garage con `--no-enable-versioning`, pero el campo `server_release` seguira diciendo MinIO.
- Un fallo de arranque de Garage no bloquea el backend (no esta en su `depends_on`).
- Garage bucket por defecto solo en el primer arranque con volumenes vacios; si ya existe, la clave y el bucket se conservan.
