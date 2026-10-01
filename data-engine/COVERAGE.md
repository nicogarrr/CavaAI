# Cobertura de data-engine

Teniamos 2585 tests y 0 % de medicion. "Los tests pasan" no dice nada de si el
codigo nuevo esta probado. Este documento explica que se mide, que se excluye y
por que, cuales son los umbrales y como reproducirlos.

## Como se mide

```bash
cd data-engine
python -m pip install pytest-cov            # ver INTEGRACION PENDIENTE
python scripts/run_coverage_gate.py          # mide + gatea (lo que usa CI)
python scripts/run_coverage_gate.py --report # imprime y sale 0 siempre
```

`scripts/run_coverage_gate.py` es un wrapper de `pytest` que anade `--cov` y luego
compara el resultado contra `coverage_baseline.json`.

**`--cov` NO esta en `addopts`.** A proposito: `python -m pytest` a secas es lo que
ejecutan `ci.yml`, `CONTRIBUTING` y las plantillas de PR, y meter `pytest-cov` en
`addopts` haria que esos comandos exploten con `unrecognized arguments` en
cualquier entorno que no lo tenga instalado. La medicion es opt-in.

## Cifra real (linea base, medida)

Medido con `branch = True` y `include_namespace_packages = True`, sobre la suite
completa en el commit base de este trabajo.

**Cobertura total: 81.49 %** — 30403 de 37310 operaciones (sentencias + ramas).

Desglose de coverage.py: sentencias **83.39 %** (24179/28996), ramas **74.86 %**
(6224/8314), 22 lineas excluidas por `exclude_lines`. El gate usa el
combinado **81.49 %**, que es el mismo `percent_covered` que publica coverage.py.
Gatear solo sentencias daria 83.39 %, mas alto y menos honesto: se pagaria el
coste de `branch = True` y no se gatearian las ramas.

| Paquete | % (sent+ramas) | Operaciones | Umbral (minimo) |
|---|---:|---:|---:|
| `app/services` | 86.45 % | 25432 | 86 |
| `app/valuation` | 95.25 % | 589 | 95 |
| `app/valuation/engines` | 87.03 % | 794 | 87 |
| `app/workflows` | 92.55 % | 443 | 92 |
| `app/api/routes` | 67.97 % | 4112 | 67 |
| `app/models` | 100.00 % | 1346 | 100 |
| `app/schemas` | 100.00 % | 612 | 100 |
| `app/api` | 100.00 % | 41 | 100 |
| `app/data` | 100.00 % | 1 | 100 |
| `app` (`seed.py`) | 100.00 % | 29 | 100 |
| `app/core` | 87.30 % | 764 | 87 |
| `app/llm` | 78.93 % | 707 | 78 |
| `app/workers` | 53.90 % | 1269 | 53 |
| `alembic` | 1.88 % | 1171 | **exento** (ver abajo) |
| **TOTAL** | **81.49 %** | **37310** | **81** |

Tiempo de suite con cobertura: **12 min** de reloj (724 s) en Windows con 16
agentes mas corriendo en la misma maquina; el `--collect-only` pelado son 89 s, y
la suite sin instrumentar anda en el mismo orden de magnitud. En un runner
`ubuntu-latest` de GitHub se espera menos, pero el job tiene `timeout-minutes: 45`
por si acaso.

## Umbrales: por que son estos

El umbral **no es un objetivo**: es `floor(linea_base) - max_drop_points`, con
`max_drop_points = 0` en todas partes. Redondear hacia abajo regala hasta 1 punto
de holgura por paquete, que absorbe el ruido normal de medicion sin permitir que
la cobertura caiga de verdad.

Dos redes, y las dos hacen falta:

1. `fail_under = 83` en `.coveragerc` ([report]). Es la red simple: `coverage
   report` y `pytest --cov` fallan por debajo de 83 sin mirar el baseline.
2. Ratchet por paquete en `scripts/run_coverage_gate.py`, leyendo
   `coverage_baseline.json`. Es la red que nombra al culpable.

Consecuencia asumida de los umbrales a 100 % (`app/models`, `app/schemas`,
`app/api`, `app/data`, `app`): **anadir una sola linea sin cubrir en cualquiera
de esos paquetes falla el gate**. Es lo correcto — son ficheros declarativos, y
protegerlos con tests es barato — pero significa que un paquete al 100 % es
fragil ante un test que se vuelva flaky o no se ejecute. Si eso molesta, la via
es `exempt` con motivo escrito, no subir el numero a mano.

### `alembic` esta exento, y por que

`alembic/` se mide y se reporta, pero no gatea. La razon es tecnica y
verificable: los tests lanzan `python -m alembic upgrade head` en **subproceso**
(`tests/test_migrations.py`, `test_0030_migration_preexisting_data.py`,
`test_0017_destructive_migration_documented.py`,
`tests/test_tenant_scoped_uniques.py`) y coverage **no instrumenta subprocesos**.
De 46 ficheros de migracion, solo 2 registran ejecucion en el proceso que se
mide. Por eso el 1.88 % no significa "las migraciones no se testean": significa
"las migraciones se testean en un proceso que coverage no ve".

Gatearlo asi seria un ratchet **insatisfacible**: cada migracion nueva baja el
paquete a 0 de lo que se ve, el gate falla, y no hay forma legitima de
recuperarlo sin importar la migracion a mano en un test. Un umbral que nunca se
puede cumplir es tan decorativo como uno que nunca falla.

La exencion esta en `coverage_baseline.json` y **exige un motivo escrito no
vacio**: el gate rechaza un `exempt` sin `reason`.

## Que se excluye, y por que

- `evals/**` — es harness de evaluacion, no producto. Ademas lo comparten otros
  agentes en paralelo; medirlo haria el gate fragil. Queda fuera de `source`.
- `tests/**` — los tests no se auto-cubren.
- `scripts/**` — utileria de repo (`sync_requirements.py`, backfills, ingestas).
  No es codigo de producto.
- `modules/**` — compatibilidad heredada; no lo importa `app/`.
- `quantstats/**` — third-party vendorizado.
- `__pycache__`, `site-packages`, `alembic/script.py.mako` — no son codigo.
- `main.py` — **no se mide, con un motivo medido, no por criterio**. En cuanto
  `source` incluye un modulo (`main.py`) junto a cualquier entrada de `omit`,
  coverage resuelve el source con `import main` durante su arranque; eso arrastra
  `app.services.rag` -> `qdrant_client` -> `numpy`, que queda registrado a medias
  en `sys.modules`, y el primer import de los tests vuelve a ejecutar el init de
  la extension `numpy._core._multiarray_umath`. CPython lo rechaza con
  `ImportError: cannot load module more than once per process`. Reproducido 3/3
  con `main.py` y 0/3 sin el. Se aceptan 230 lineas de entrypoint fuera de la
  cifra gateada hasta que haya forma de instrumentarlo sin ese conflicto.

## `include_namespace_packages`: la opcion que mas importa

`include_namespace_packages = True` (en `[report]`, **no** en `[run]`) no es
cosmetica. `coverage.files.find_python_files()` hace `os.walk` y **poda todo
subdirectorio sin `__init__.py`**. Sin esta opcion, los ficheros nunca importados
de esas carpetas desaparecen en silencio del denominador. Aqui arrastraba a
`app/core`, `app/data` y `alembic/versions` (46 ficheros), y mediando la primera
vez salia un 86.37 % de solo sentencias **falso**: las 46 migraciones no
contaban. Peor todavia: anadir codigo nuevo sin tests en una de esas carpetas no
habria movido el numero, que es justo lo que este gate tiene que cazar. Con la
opcion, el denominador es el codigo real: 28996 sentencias y 37310 operaciones
(sentencias + ramas) en vez de las 27996 que se veian antes.

## `exclude_lines`

Solo codigo que no se puede ejecutar de forma significativa en un test unitario:
`# pragma: no cover`, `if TYPE_CHECKING:`, `@overload`, `raise NotImplementedError`,
`if __name__ == "__main__":` y `except (ImportError, ModuleNotFoundError)`.
La excepcion de imports opcionales cubre la rama de degradacion cuando una
dependencia no esta, que no es un hueco de test. **No se excluye `app/llm/*`**:
es logica de negocio pura (contracts, routing, factory, jev, json), sin I/O, y
esta al 84.04 %. Excluirla habria sido excluir justo lo que conviene proteger.

## Tests que necesitan servicios

- **Qdrant**: `tests/test_rag_activation.py` es el **unico** fichero con
  dependencia real de un servicio. Tres tests llevan un `skipif` local
  (`requires_qdrant`, reason "Qdrant no disponible en localhost:6333"), asi que se
  auto-excluyen: sin Qdrant skip, con Qdrant corren. `ci.yml` los corre con
  servicio Qdrant y `CAVAAI_ENABLE_VECTOR_*=1`, y ademas **falla si se saltan**.
- **Redis / MinIO**: no hace falta servicio real. Los tests usan URLs muertas
  (`redis://127.0.0.1:1/0`) o `httpx.MockTransport`. Ver `tests/auth_helpers.py`,
  `tests/test_rate_limit.py`, `tests/test_security_fixes.py`.
- **Postgres**: el job `migrations` de `ci.yml` si lo levanta, pero el job de
  cobertura **no**: la linea base se midio sin el.

Por eso el job de cobertura corre con `CAVAAI_ENABLE_VECTOR_* = 0` y **sin
contenedor de Qdrant**: la medicion tiene que ser determinista. Si el gate
midiera con Qdrant en local y sin el en CI, la linea base no valdria para nadie.

El runner acepta argumentos extra de pytest, que es donde encaja un
`-m "not services"`:

```bash
python scripts/run_coverage_gate.py -- -m "not services"
```

Hoy `-m "not services"` es un **no-op**: ningun test lleva ese marker, luego no
deselecciona nada (propiedad segura). Ver `INTEGRACION PENDIENTE`.

## Por que el gate es fail-closed

Ante la duda, falla. Y falla **antes** de dejar pasar nada:

| Situacion | Que hace |
|---|---|
| `coverage_baseline.json` no existe | falla, y dice como generarlo |
| JSON invalido / no es objeto | falla |
| Version de baseline desconocida | falla |
| `packages` vacio | falla |
| Clave desconocida (un typo) | falla |
| Paquete con `coverage` no numerico, o fuera de `[0, 100]` | falla |
| `exempt` sin `reason` no vacio | falla |
| Paquete medido **sin** linea base | falla: obliga a declararlo |
| Paquete del baseline **que no se mide** | falla: obliga a podarlo |
| Informe sin `files` / sin `summary` | falla |

Un paquete nuevo sin declarar no se "deja pasar": o lo declaras con su umbral, o
lo marcas `exempt` con motivo escrito. Un typo en una clave no se ignora, porque
un typo silencioso es cobertura que no se gatea sin que nadie lo note.

`evaluate()`, `load_baseline()`, `aggregate_by_package()`, `render_baseline()` y
`format_report()` son funciones puras sobre un dict: por eso
`tests/test_coverage_gate_contracts.py` (33 tests) las ejerce todas sin correr la
suite, y por eso el gate esta verde en segundos cuando el numero se ha roto.

### El gate no depende de que los tests pasen

La cobertura se evalua **siempre**, tambien con pytest en rojo. Gatear la medicion
sobre "los tests pasaron" haria que un fallo de suite dejara el gate ciego, que es
justo cuando mas falta ver si la cobertura se movio. El codigo de salida de pytest
se reporta y hace fallar el gate igualmente. `--report` es la excepcion
documentada: imprime y sale 0, porque responde a "¿cuanto cubrimos hoy?".

## INTEGRACION PENDIENTE

Dos cambios de una linea cada uno, ambos en ficheros que en esta tarea pertenecen
a otro agente:

1. **`pytest-cov` no esta declarado en ningun sitio.** Va en
   `data-engine/pyproject.toml`, en `[project.optional-dependencies]`:

   ```toml
   [project.optional-dependencies]
   test = ["pytest>=8.0.0", "httpx>=0.27.0", "pytest-cov>=5.0"]
   ```

   **No** en `requirements.txt`: el job `dep-parity` corre
   `python data-engine/scripts/sync_requirements.py --check`, que exige paridad
   exacta y bidireccional entre `pyproject [project].dependencies` y
   `requirements.txt`. Como `sync_requirements.py` **no** inspecciona
   `[project.optional-dependencies]`, anadirlo ahi es la unica forma de que
   `pip install -e .[test]` traiga el gate sin romper la paridad. El job de
   coverage lo instala con `pip install ... pytest-cov` en su propia linea.

2. **Registrar el marker `services`** en
   `data-engine/pyproject.toml` -> `[tool.pytest.ini_options]`:

   ```toml
   markers = ["services: requiere un servicio externo vivo (Qdrant, Postgres)"]
   ```

   Y despues marcar `@pytest.mark.services` los tests de
   `tests/test_rag_activation.py` (hoy solo auto-skipean con un `skipif` local, que
   no se puede seleccionar con `-m`). Sin registrarlo, pytest avisa con
   `PytestUnknownMarkWarning` en cuanto se use.

3. **Sugerencia de `.gitignore`** (no bloqueante): `data-engine/.coverage` no esta
   ignorado. Como esta tarea no podia tocar `.gitignore`, el fichero de datos va a
   `data-engine/htmlcov/.coverage` (`data_file` en `.coveragerc`), que ya esta
   ignorado por la linea 76. Con una entrada `data-engine/.coverage` se podria
   volver a la ruta por defecto de coverage.

4. `data-engine/pyrightconfig.json` solo incluye `["app", "main.py", "routers"]`,
   asi que `scripts/` y `tests/` no se type-chequean: `run_coverage_gate.py` esta
   fuera del chequeo de pyright. No es un problema (ruff si lo cubre) pero queda
   dicho.

## Nota sobre fallos preexistentes

En el commit base (`0be7186c`) la suite ya venia con **14 tests rojos**, sin
relacion con la cobertura: 13 en `tests/test_retitle_sec_news_es.py` y 1 en
`tests/test_company_snapshot_batch.py` (comparacion de `recent_changes` que no
coincide). Se reproducen igual con `python -m pytest` sin `--cov`. El job de
cobertura saldra en rojo por ellos hasta que se arreglen, con el informe de
cobertura igualmente impreso antes de fallar.
