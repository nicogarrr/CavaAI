# ADR-001: Facts SEC publicos compartidos entre tenants

- Estado: PROPUESTO (diseno; implementacion en PRs incrementales tras OK)
- Fecha: 2026-09-28
- Decisor: Nico (aprobada la direccion "compartidos" el 2026-09-28; este ADR fija el diseno concreto)

## Contexto

Hoy `companies` es global pero `financial_facts` va por tenant (`tenant_id`,
filtro global `_scope_tenant_queries`). Consecuencias observadas en prod:

- Cada tenant ingesta y almacena los mismos facts SEC de las mismas empresas
  (trafico SEC y storage duplicados por tenant).
- Cobertura desigual por tenant: el tenant 2 tiene V completo (FY2019-2025)
  mientras el tenant 5 solo tenia lo que escribio la ruta de evidencia de
  tesis (1 año por metrica, anclado a FY2020) - origen del bug F349.
- Los backfills de recencia (F352/F353) hay que repetirlos por tenant.

Los facts SEC (XBRL companyfacts) son datos PUBLICOS e identicos para cualquier
tenant: no hay razon de aislamiento para duplicarlos.

## Decision

Los facts de fuente publica SEC se comparten entre tenants en un ambito sin
`tenant_id` (compartido). Lo privado NO se mueve: posiciones, tesis,
watchlists, evidence_suggestions, KPI candidates, alertas y cualquier dato
derivado de actividad del usuario siguen estrictamente aislados por tenant.

Criterio de clasificacion (fail-closed): un dato solo es compartido si (a)
proviene de una fuente publica (SEC EDGAR), (b) no incorpora nada aportado
por un usuario, y (c) su clave natural es (company, metric, period, source).
Ante la duda, el dato permanece por tenant.

## Diseño

- `financial_facts.tenant_id` pasa a ser NULL para facts publicos SEC; el
  filtro de ambito lee `(tenant_id = :tenant OR tenant_id IS NULL)` SOLO
  para la tabla financial_facts (y futuras tablas declaradas compartidas).
  OJO: `tenant_id IN (:tenant, NULL)` NO funciona en SQL (NULL nunca
  iguala) - la forma correcta es el OR explicito, con pruebas en Postgres
  (no solo sqlite) antes de mergear la fase 1. Escrituras de datos
  privados jamas admiten NULL.

### Identidad del hecho SEC (dedup y restatements)

La clave natural de un fact SEC NO es solo (company, metric, period): dos
filings pueden reportar la misma metrica y periodo con valores DISTINTOS
(restatements y correcciones). La identidad del hecho es:

  (company_id, metric/concepto XBRL, periodo (fiscal_year, fiscal_quarter,
  end date), unidad, valor, filing de origen (accession number), fecha del
  filing)

Regla de revision temporal: un restatement (mismo concepto/periodo/unidad,
filing MAS reciente, valor distinto) NO se deduplica contra el anterior -
conviven y la lectura toma el del filing mas reciente (regla de recencia
F352/F353 vigente). Antes de crear cualquier constraint unico o borrar
duplicados del historico (fase 3), se ejecuta una prueba de discrepancias
sobre prod: cuantos grupos (company, metric, periodo, unidad) tienen
valores distintos entre tenants/filings. Ese conteo decide la clave final
del unique y se reporta antes de tocar nada (regla de alcance exacto).

### Provenance cross-tenant

`financial_facts.source_id` apunta a `documents.id` y Document ES
tenant-owned: si un fact consolidado queda en NULL pero su Document es
privado de un tenant, el resto no puede resolver su provenance y,
peor, el Document podria filtrarse como referencia global.

Separacion ANTES de la migracion:
- La provenance canonica de un fact SEC compartido es el FILING PUBLICO:
  accession number SEC + URL de EDGAR + fecha de filing + concepto XBRL,
  almacenados en columnas propias del fact (o tabla sec_filings
  compartida). Es verificable por cualquier tenant contra la fuente
  publica sin tocar datos de otro tenant.
- El Document interno queda como referencia OPCIONAL y privada del tenant
  que lo ingesto (segundo plano); nunca es la unica provenance de un fact
  compartido. Si la provenance publica no esta completa para una fila, la
  fila NO se consolida a NULL en fase 3 (se queda por tenant hasta
  completarla).

## Plan de migracion (fases, cada una su PR)

1. Lectura dual: el scope de financial_facts admite NULL compartido; las
   escrituras siguen por tenant. Sin cambio de datos. Tests de aislamiento:
   un tenant nunca ve datos privados de otro ni puede escribir en NULL.
2. Escritura compartida para SEC: la ingesta SEC escribe con tenant_id
   NULL y deduplica SOLO contra observaciones SEC con provenance publica
   verificada (accession + concepto + unidad + periodo + fecha de filing,
   ver Diseño). Una fila historica por tenant NO se usa como referencia de
   dedup salvo que su provenance publica este completa; si no lo esta, la
   observacion nueva se escribe en NULL sin tocarla y quedan como dos
   filas hasta la fase 3. En ningun caso un fact NULL referencia un
   Document privado: su source_id es NULL y la provenance vive en sus
   columnas publicas.
3. Migracion de historico: backfill que consolida duplicados cross-tenant
   SOLO entre filas con provenance publica completa y coincidente (mismo
   accession/concepto/unidad/periodo/valor). Criterio de supervivencia:
   la fila con provenance publica completa y valor identico al filing;
   NUNCA se elige una fila "por tener source_id" (ese criterio premiaba
   el FK a Document privado). La fila consolidada se mueve a NULL con
   source_id NULL: el source_id privado de cada copia NO se referencia
   globalmente; si un tenant quiere conservar ese enlace interno se
   preserva en una tabla de mapeo privada del tenant
   (fact_consolidation_map: tenant_id, fact_id_compartido, document_id,
   visible solo para ese tenant) antes de borrar la copia. Las copias por
   tenant se borran tras verificar conteos; filas sin provenance publica
   completa NO se consolidan (quedan por tenant). Con snapshot de
   respaldo previo y conteo verificado (misma disciplina que la limpieza
   F350).
4. Limpieza: retirar la escritura por tenant de facts SEC y los backfills
   por tenant redundantes.

## Rollback

- Fase 1 (lectura dual): flag de configuracion; apagar vuelve a lectura
  solo-tenant sin tocar datos. Sin perdida: aun no se ha escrito nada en
  NULL.
- Fase 2 (escritura compartida): el flag solo detiene escrituras NUEVAS;
  los facts ya escritos en NULL se volverian invisibles al apagar la
  lectura dual. Para que el rollback sea sin perdida se exige UNA de:
  (a) dual-write temporal (tenant + NULL) durante la fase 2 con job de
  limpieza de la copia tenant al cerrar la fase, o (b) lectura dual
  MANTENIDA hasta que un backfill de reversion haya copiado los facts
  NULL de vuelta al tenant propietario. La opcion concreta se decide en
  la PR de fase 2 con los conteos de volumen en la mano.
- Fase 3: la consolidacion de historico es destructiva sobre duplicados;
  se ejecuta con tabla de respaldo (id + fila completa) y verificacion de
  conteos, reversible con un restore desde esa tabla. Filas sin
  provenance publica completa NO se consolidan (ver Diseño).

## Tradeoffs y riesgos

- Storage: baja (una copia por observacion publica, no una por tenant).
- Frescura: sube (un solo backfill SEC actualiza a todos los tenants).
- Riesgo de fuga cross-tenant: acotado a datos PUBLICOS por construccion
  (criterio fail-closed); los tests de aislamiento de la fase 1 son la
  barrera permanente en CI.
- Riesgo de colision de escritura: dos tenants ingiriendo lo mismo a la vez;
  la dedup por clave natural + constraint unico lo resuelve.
- Coste de migracion del historico: una pasada con respaldo; ventana corta.

## Validacion

- Tests de aislamiento (privado nunca cruza; NULL nunca escribible desde
  rutas privadas), tests de dedup (misma clave natural = una fila), y
  verificacion en prod post-fase-3: V/MSFT con FY completo en todos los
  tenants sin duplicados cross-tenant.
