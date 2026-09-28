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
  filtro de ambito lee `tenant_id IN (:tenant, NULL)` SOLO para la tabla
  financial_facts (y futuras tablas declaradas compartidas). Escrituras de
  datos privados jamas admiten NULL.
- Clave de deduplicacion global: (company_id, metric, period, fiscal_year,
  fiscal_quarter, source_type, is_adjusted) - la misma observacion publica no
  se inserta dos veces venga del tenant que venga.
- Provenance intacta: cada fact conserva source_id/source_type/filing de
  origen; compartir no borra trazabilidad (regla de veracidad vigente).

## Plan de migracion (fases, cada una su PR)

1. Lectura dual: el scope de financial_facts admite NULL compartido; las
   escrituras siguen por tenant. Sin cambio de datos. Tests de aislamiento:
   un tenant nunca ve datos privados de otro ni puede escribir en NULL.
2. Escritura compartida para SEC: la ingesta SEC escribe con tenant_id NULL y
   deduplica contra la clave global (tenga el fact el tenant que tenga).
3. Migracion de historico: backfill que consolida duplicados cross-tenant
   (misma clave natural): se queda la fila mas completa (con source_id), se
   mueve a NULL y se borran las copias por tenant. Con snapshot de respaldo
   previo y conteo verificado (misma disciplina que la limpieza F350).
4. Limpieza: retirar la escritura por tenant de facts SEC y los backfills
   por tenant redundantes.

## Rollback

- Fases 1-2: flag de configuracion (shared SEC facts on/off); apagar vuelve
  a la lectura solo-tenant sin tocar datos.
- Fase 3: la migracion de historico es destructiva sobre duplicados; se
  ejecuta con tabla de respaldo (id + fila completa) y verificacion de
  conteos, reversible con un restore desde esa tabla.

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
