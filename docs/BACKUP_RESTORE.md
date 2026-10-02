# Backup y Restore

Hay DOS caminos y solo uno está **verificado**. Este documento dice cuál es
cuál, qué garantiza cada uno y qué no garantiza ninguno.

| Camino | Qué es | ¿Verificado? | Dónde |
|---|---|---|---|
| **Python (el bueno)** | Backup de los 3 pilares con manifiesto común, SHA-256 por artefacto, restore a destino limpio y **6 comprobaciones fail-closed** | **Sí**: drill de desastre ejecutable + CI lo corre en cada push | `data-engine/scripts/backup/`, `data-engine/scripts/restore/` |
| **Bash/PowerShell (heredado)** | `pg_dump` + `tar` de los volúmenes de MinIO/Qdrant/DuckDB | **No verifica nada**. Sirve para la VM de producción y para la copia fuera de máquina | `scripts/backup.sh`, `scripts/restore.sh`, `scripts/backup.ps1`, `scripts/restore.ps1` |

La regla: **un backup que no se ha restaurado y verificado no es un backup**.
Por eso el camino bueno es el que se prueba, y por eso los scripts de bash
siguen existiendo pero ya no son el camino del que dar fe.

---

## 1. El camino verificado (Python)

Todo se ejecuta desde `data-engine/`. Requisitos: Python 3.11+ con las
dependencias del engine (`minio`, `httpx`, `psycopg`, `sqlalchemy`, `alembic`),
Docker para el modo contenedor, y las variables del entorno donde corra.

```bash
cd data-engine

# Backup de los tres pilares (Postgres, MinIO, Qdrant) -> <backup>/manifest.json
python -m scripts.backup.backup_all --out-dir backups

# Restore a destino limpio (DESTRUCTIVO: exige --confirm-restore)
python -m scripts.restore.restore_postgres --manifest backups/<id> --mode docker --container cavaai-postgres --confirm-restore
python -m scripts.restore.restore_minio    --manifest backups/<id> --endpoint 127.0.0.1:9000 --confirm-restore
python -m scripts.restore.restore_qdrant   --manifest backups/<id> --url http://127.0.0.1:6333 --confirm-restore

# Verificación: 6 comprobaciones, fail-closed (una omitida = fallo)
python -m scripts.restore.verify_restore --manifest backups/<id> \
  --mode docker --pg-container cavaai-postgres \
  --minio-endpoint 127.0.0.1:9000 --qdrant-url http://127.0.0.1:6333 \
  --app-base-url http://127.0.0.1:8000

# Ciclo completo de desastre, aislado (nunca sobre datos reales)
python -m scripts.backup.disaster_drill
```

El runbook paso a paso (qué hacer con la app caída, en qué orden, con qué
tiempos estimados) está en
[`data-engine/scripts/backup/RUNBOOK.md`](../data-engine/scripts/backup/RUNBOOK.md),
y el por qué de cada decisión técnica en
[`data-engine/scripts/backup/README.md`](../data-engine/scripts/backup/README.md).

### El manifiesto

Cada backup produce `manifest.json`: artefactos con su SHA-256, conteos por
tabla antes y después del dump, `alembic_version` del head, objetos de MinIO con
hash por clave, colecciones de Qdrant con sus puntos, y valores sonda (los
tickers que la comprobación `d_aplicacion` exige ver servidos). Sin manifiesto
no hay backup: los restores y la verificación trabajan contra él, no contra lo
que crean que había.

### Las 6 comprobaciones, y por qué son fail-closed

`verify_restore.py` ejecuta seis comprobaciones y **ninguna puede quedar
"omitida"** (mismo criterio que el gate de RAG de `ci.yml`: un test que se salta
es un gate que no existía):

| Check | Qué compara |
|---|---|
| `a_esquema` | Las tablas del dump (`pg_restore --list`) contra las del manifiesto y las de la base restaurada |
| `b_conteos` | Los conteos por tabla del manifiesto contra la base restaurada: desviación distinta de 0 es fallo |
| `c_alembic` | El `alembic_version` restaurado contra el del manifiesto (y el head del código de esa máquina) |
| `d_aplicacion` | La app ARRANCADA contra la base restaurada: `/health/ready`, snapshot de compañía y los tickers sonda del manifiesto servidos por la API |
| `e_objetos` | Cada clave de MinIO con su SHA-256 recalculado en el destino |
| `f_vectores` | Colecciones de Qdrant, sus puntos y el `checksum` del snapshot |

Verificación **en dos fases**, porque arrancar la app muta la base restaurada
fuera de producción (`main.py` llama a `ensure_company_master()` si
`APP_ENV != production`): `--phase data` (a, b, c, e, f) va **antes** del
arranque y `--phase app` (d) **después**. Comparar conteos con la app en marcha
daría un falso positivo de «restore incompleto» o taparía una pérdida real.

Si falta `--app-base-url`, `d_aplicacion` **falla** con el motivo. No se salta.

### MinIO: por objeto y con versionado de bucket

Un `tar` del volumen de MinIO **no es un backup**: solo restaura en la misma
máquina, contra el mismo `/data` y con el mismo `.minio.sys`. El camino bueno
copia objeto a objeto, direccionado por clave, con SHA-256 por clave.

**El versionado del bucket** lo activa `backup_minio.py` de forma idempotente
antes de copiar y comprueba que quedó activo; si no puede, falla. Sin
versionado, «recupera el objeto que se sobrescribió hace una hora» es
imposible: la copia buena sería solo el estado actual. El repo no lo activaba
(`document_store.py` hace `make_bucket` y nada más), así que la garantía la
pone el backup, no la aplicación.

Dos transportes, ambos con versión declarada en el manifiesto:

- `sdk` (por defecto): cliente `minio` de Python, sin exigir `mc` en el host.
  Es el que usan el drill y CI.
- `mc`: `mc mirror` para sacar el backup fuera de la máquina cuando `mc` ya está
  configurado (`--transport mc --mc-alias ...`). No es el camino por defecto
  porque `mc` no está en la imagen de MinIO y exigirlo rompe la primera
  máquina que no lo tenga.

### Qdrant: snapshot por API, no copia del volumen

`POST /collections/{c}/snapshots` + descarga del `.snapshot`, y el restore sube
cada snapshot por la API. Es lo único que restaura el índice en otra máquina:
copiar `/qdrant/storage` solo funciona en la misma máquina y con el mismo path.
El `checksum` que devuelve Qdrant **sí** es el SHA-256 del `.snapshot` y se
comprueba contra el fichero descargado.

### Postgres: `pg_dump -Fc` + globals + head de Alembic

Dump en formato custom (restaurable por partes, catalogable con
`pg_restore --list`), globals aparte (`pg_dumpall --globals-only`: sin el rol,
el restore «funciona» y el backend falla con `role does not exist` en el primer
arranque) y **rechazo** de bases por detrás del head de Alembic
(`--allow-schema-drift` lo permite a propósito). Los conteos se leen antes y
después del dump; si no coinciden, el backup **falla** en vez de emitir un
artefacto dudoso.

---

## 2. Los scripts en bash/PowerShell (la VM de producción)

`scripts/backup.sh` / `scripts/restore.sh` (y sus primos `.ps1`) siguen siendo
válidos para la VM de Oracle y para el flujo de Windows local: `pg_dump -Fc`,
snapshots de Qdrant, tar de MinIO y DuckDB, manifest por backup, restore con
`--confirm-restore`, y subida a Cloudflare R2 si se define `RCLONE_REMOTE`.

Lo que **no** hacen: **verificar nada**. No recalculan hashes contra un
manifiesto, no comprueban el head de Alembic, no restauran a destino limpio ni
ejecutan las 6 comprobaciones. Un `tar` del volumen de MinIO restaura solo en
esa misma máquina. Son transporte y respaldo, no evidencia de que la
recuperación funciona.

Guía de la VM completa: [`docs/oracle-setup.md`](oracle-setup.md).

DuckDB y ficheros locales (`/data/analytics.duckdb`, `data-esef-snapshots`) los
cubre **solo** este camino: el árbol Python no los toca a propósito (no son de
los tres pilares y su restauración no se ha verificado).

---

## 3. El restore drill de CI

`.github/workflows/restore-drill.yml` ejecuta el ciclo completo —seed
determinista (12 companies, 7 objetos, 25 puntos), backup, **destrucción de
contenedores y volúmenes**, restore a destino limpio y las 6 comprobaciones—
en un entorno efímero de `ubuntu-latest`, **en cada push**. Falla si alguna
comprobación se omite o si la desviación de conteos no es 0.

- **No es bloqueante de PR y sí de main**: son ~10 minutos en runner frío (torch
  CPU incluido). El gate que sí bloquea el PR es
  `tests/test_backup_contracts.py` (segundos, en el job `backend` de `ci.yml`),
  que fija el contrato sin levantar servicios. En `main` sí bloquea: ahí es
  donde un restore roto tiene que parar el pipeline.
- `disaster_drill.py` es la versión local del mismo ciclo: contenedores,
  volúmenes, puertos y temporales propios (`cavaai-drill<id>-*`), aborta si ya
  existe uno con ese nombre y no menciona ningún volumen de producción (hay un
  test que lo comprueba).

---

## 4. Retención y copia fuera de máquina

- **Local (`backups/`)**: `backup.sh` conserva los últimos
  `${BACKUP_RETENTION_COUNT:-8}` backups y solo purga tras una ejecución
  correcta (con `set -e`, un fallo no borra nada). El árbol Python no limpia
  nada a propósito: borrar backups es destructivo y no debe depender de un
  script que nadie ha leído.
- **Fuera de la máquina**: el manifiesto y los artefactos se copian tal cual
  (checksums incluidos) y `backup.sh` los replica a R2 con `rclone` (retención
  por lifecycle del bucket, p. ej. 30 días; `rclone copy` nunca borra). Conviven:
  el árbol Python produce el backup verificable, el bash lo replica.
- **Producción**: copia siempre a almacenamiento cifrado fuera del host Docker,
  y practica el restore (el drill de CI es automático; el manual, al menos
  trimestral).

## 5. Lo que no cubre este documento

- **MongoDB**: vive en MongoDB Atlas y lo respalda el proveedor. Si vuelve a ser
  local, necesita su propio pilar.
- **La copia cifrada fuera de máquina** como tal: aquí se dice que debe existir,
  no cómo se configura el bucket (eso vive en la guía de la VM).
