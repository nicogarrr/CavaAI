# Estados degradados: cerrar los intermedios (decisión de producto)

**Fecha:** 2026-10-01 · **Ámbito:** UI (ProPicks, Impuestos, Insider, asistente de Research)

## El problema

La Honestidad Epistemológica del repo tiene un patrón propio: cuando un dato no
existe, la UI lo **declara** en vez de disimularlo. Lo que se había acumulado es
una cuarta categoría, la peor de las cuatro: el estado **intermedio**, que ni
miente ni informa. Su fórmula es siempre la misma — *« aún no», «pendiente de
validación», «se publicará cuando…», «faltan datos»* — y tiene un problema
estructural: **promete un trabajo futuro que nadie ha contratado**. Un usuario
que lea «se publicará cuando existan fundamentales point-in-time» no puede
saber si es una semana o un sitio que jamás va a existir, y la app tampoco.

Regla que sale de esta revisión:

> Un estado degradado tiene dos salidas: el **dato real** (si existe y es
> alcanzable con lo ya implementado) o un **copy definitivo** que explique por
> qué falta y qué haría falta, sin prometer entrega. «Pendiente» desaparece.

## Decisiones

| # | Estado intermedio | Decisión | Razón |
|---|---|---|---|
| 1 | Ficha de estrategia: «aún no tiene selección ni backtest publicados… en cuanto estén disponibles» | **Dato real + copy definitivo** | El backtest por estrategia no existe y no se va a publicar: el embudo persiste **un único run**, así que no hay fundamentales con fecha de corte. La ficha pasa a mostrar lo que sí es dato real (los pesos por categoría y el score mínimo del catálogo) y declara por qué no hay cifras. |
| 1b | Walk-forward sin meses: agregados a 0 leídos como «0,00 %» | **Copy definitivo** | Se declara que ningún corte superó el mínimo de sesiones y **no se muestran ceros**: un 0,00 % sin meses detrás es el peor falso dato posible. |
| 2 | Rebalanceo: «Aún no hay snapshot del mes anterior» | **Copy definitivo + arreglo de dato** | CavaAI no guarda histórico de meses (solo el último run): no es un estado que se resuelva solo, es arquitectura. Y, sobre todo, el diff contra vacío pintaba **toda la cartera como «Entra»**; sin mes anterior la lista ahora es «Selección vigente», sin entradas ni salidas que atribuir. |
| 3 | Caja del embudo: «Valoración y momentum: neutras…» | **Dato real (derivado)** | Era un literal fijo sobre un run concreto: el día que el embudo trajera CFROI/WACC o momentum, seguiría mintiendo. Ahora la frase se deriva de los picks (`categoryNeutralNote`) y nombra la entrada que falta de cada categoría. |
| 4 | Impuestos: «No disponible para este ejercicio», «mapeo no verificado», «Descarga pendiente de validación» | **Dato real + copy definitivo** | El backend **ya devuelve el contenido del fichero 720** (`file720.content`, ISO-8859-1, diseño oficial). La UI lo bloqueaba prometiendo una revisión futura: ahora se descarga el contenido real, etiquetado como ayuda de cómputo y con las notas del propio generador. Los bloqueos del IRPF muestran el motivo real del backend y, si falta, qué haría falta. |
| 5 | Insider: «lectura durable no disponible (OperationalError)» con «0 filings persistidos» | **Copy definitivo + arreglo de dato** | La lectura durable consulta la tabla de filings persistidos, no EDGAR. Con `status != ok` ese `0` no es un recuento: la UI ya no lo pinta como número y explica que es un fallo de lectura (no «no hay Form 4») y que las señales de arriba no dependen de esa tabla. |
| 6 | Asistente: respuesta vacía → «Sin datos» | **Copy definitivo** | El contrato permite `answer: ''` y distingue `answered` de `insufficient_data`. Un «Sin datos» a secas mezclaba tres casos distintos; ahora cada uno se nombra y se dice dónde está la información que sí hay. |

## Lo que NO se toca

- **`app/(public)/terms/page.tsx`**: su comentario de «pendiente de validación
  por el dueño» es legal y se resuelve en otra fase. Se verificó que **no hay
  ningún otro «pendiente de validación» de copy legal** en el repo (búsqueda
  sobre `app/`, `components/` y `lib/`): el único hit es ese comentario.
- Archivos con otro dueño en curso (`ThesisMemo.tsx`, `PortfolioTransactions.tsx`,
  `PersonalizedOverview.tsx`, `app/(root)/screener/**`, `components/screener/**`,
  `AlertsManager.tsx`, `lib/format.ts`, `lib/labels.ts`, `lib/glossary.ts`,
  `lib/i18n/**`, `package.json`, `.github/workflows/**`,
  `scripts/check-i18n.mjs`).

## Guards

| Guard | Qué impide volver atrás |
|---|---|
| `scripts/no-pending-state-copy-guard.test.ts` | Copia de promesas de futuro («pendiente de validación», «se publicará cuando», «en cuanto estén disponibles», «aún no hay snapshot»…) en las nueve piezas degradadas. |
| `scripts/propicks-definitive-state-guard.test.ts` | Ficha, walk-forward y rebalanceo: la ficha sin «Sin datos» + motivo real, el walk-forward sin ceros, el rebalanceo sin «Entran» sobre toda la cartera. |
| `scripts/propicks-category-neutral-copy-guard.test.ts` | El copy de categorías se deriva del run (módulo puro `components/proPicks/category-display.ts`). |
| `scripts/taxes-filing-definitive-state-guard.test.ts` | El 720 no vuelve a «pendiente de validación» y la descarga entrega el contenido real en latin-1. |
| `scripts/research-assistant-empty-answer-guard.test.ts` | La respuesta/sección vacía no vuelve a «Sin datos». |
| `scripts/insider-degraded-honesty-guard.test.ts` (extendido) | La lectura durable no colapsa en «0 filings» ni en la `reason` cruda. |

Ejecución: `node --experimental-strip-types --test scripts/<guard>.test.ts`