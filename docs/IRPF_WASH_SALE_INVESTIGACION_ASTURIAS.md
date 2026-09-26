# Wash sale IRPF — Investigación España / Asturias (docs-only, sin fix)

> Rama docs-only desde `origin/main`. NO toca `data-engine/app/services/tax_report_service.py`.
> NO es asesoramiento fiscal. Requiere criterio de profesional fiscal colegiado antes de alterar la compute de declaración.
> Estado: investigación avanzada pero **NO 100% verificada** — ver §8. Por eso no hay rama de fix de código.

## 0. Objeto y decisión

- El usuario cambió la semántica wash-sale y la revirtió: el código solo bloquea si el lote sigue en cartera (`qty > 0`) tras la venta.
- La hipótesis alternativa (bloquear por mera adquisición en ventana aunque el lote ya se vendió) no se sostenía sin fuente verificada.
- Decisión correcta: **revertir y no alterar la compute fiscal sobre una lectura no verificada**.
- Esta rama solo documenta la investigación. El fix de código queda bloqueado hasta verificación 100% + dictamen profesional.

## 1. Base de código auditada

- `main` local (`b176f6f`) vs `HEAD` anterior (`feat/shell-nav-foundation`, `f5c2d4e`): el diff en `data-engine/app/services/tax_report_service.py` **no toca lógica wash-sale** — solo dividendo no-atribuido (`JOIN` → `OUTER JOIN`, `_new_cash_bucket`, `_unattributed_label`, `summary.unattributed_*`).
- Semántica vigente (también en `origin/main`, `07ae9ff`):
  - `WASH_SALE_RULE_ID = "es-irpf-2m"`, `WASH_SALE_WINDOW = relativedelta(months=2)` (`tax_report_service.py:54-55`).
  - Ventana inclusiva ambos lados; backward exige `lot.date >= venta - 2m`, `lot.capacity > 0`, `lot.qty > 0` (`:326-332`); forward consume `capacity` del lote nuevo (`:277-284`).
  - Bloqueo proporcional (`take = min(...)`); diferido se suma al coste del lote recomprado y aflora vía FIFO (`:302-305`).
  - Nunca bloquea ganancias; `wash_sale_window_open` usa `last_data_date` global (`:244,387-391`), no 31-dic; remanente abierto sigue deducido + flag.
  - Agrupa por `Company.ticker` exacto, sin ISIN, sin flag cotizado, aplica 2m a todo.
- Tests que pinan el comportamiento: `data-engine/tests/test_tax_report_service.py` WS1–WS8, `test_tax_spanish_filing.py`, `test_portfolio_fiscal_bucket.py`.

## 2. Norma estatal verificada (BOE)

Ley 35/2006 IRPF, BOE núm. 285 de 29/11/2006, ref. BOE-A-2006-20764. Redacción verificada `p=20241224` (art. 33.5 estable desde 2006):

- Art. 33.5, encabezado: "5. No se computarán como pérdidas patrimoniales las siguientes:"
- e) genérica: "Las derivadas de las transmisiones de elementos patrimoniales, cuando el transmitente vuelva a adquirirlos dentro del año siguiente a la fecha de dicha transmisión. Esta pérdida patrimonial se integrará cuando se produzca la posterior transmisión del elemento patrimonial."
- f) cotizados: "Las derivadas de las transmisiones de valores o participaciones admitidos a negociación en alguno de los mercados secundarios oficiales de valores definidos en la Directiva 2004/39/CE [...], cuando el contribuyente hubiera adquirido valores homogéneos dentro de los dos meses anteriores o posteriores a dichas transmisiones."
- g) no cotizados: idéntico con "en el año anterior o posterior".
- Párrafo común f/g: "En los casos previstos en los párrafos f) y g) anteriores, las pérdidas patrimoniales se integrarán a medida que se transmitan los valores o participaciones que permanezcan en el patrimonio del contribuyente."
- No hay letra específica de fondos en el 33.5. IIC: art. 94.1.a (FIFO + traspasos sin cómputo; ETF cotizados excluidos vía art. 79 RD 1082/2012).
- Valores homogéneos: definición reglamentaria art. 8 RD 439/2007 (BOE núm. 78, 31/03/2007, BOE-A-2007-6820): mismo emisor, misma operación financiera / unidad de propósito, igual naturaleza y régimen de transmisión, contenido sustancialmente similar de derechos y obligaciones; diferencias accesorias (importe unitario, fechas, tramos) no rompen homogeneidad.
- FIFO: art. 37.2 Ley ("cuando existan valores homogéneos se considerará que los transmitidos son los adquiridos en primer lugar") y 94.1.a para IIC.
- La Ley **no** prevé incrementar el coste con la pérdida diferida (a diferencia de IRC §1091 USA): mecanismo de diferimiento puro.

## 3. Criterio AEAT verificado directamente (resuelve el conflicto ley-literal vs código)

Fuente abierta y leída en esta sesión: Manual Renta 2025, cap. 11, "Pérdidas patrimoniales que no se computan fiscalmente como tales", actualizado 17/03/2026:

- La pérdida "deberá ser declarada y cuantificada en la declaración del ejercicio en el que se haya generado" aunque no se integre; se integra "a medida que se transmitan los valores o participaciones que permanezcan en el patrimonio".
- Procedimiento (solo en Manual 2025; el 2024 termina antes): "Se considera que existe una recompra cuando se adquieren valores homogéneos dentro de los dos meses anteriores o posteriores a la venta **y dichos valores continúan en el patrimonio del contribuyente tras la transmisión**."
- "Que después de la transmisión no queden acciones o participaciones en el patrimonio del contribuyente, en cuyo caso la pérdida patrimonial podrá imputarse íntegramente."
- Si quedan: si remanente >= comprado en 2m previos → recompra = total comprado previo; si remanente < comprado previo → recompra = remanente.
- "No se aplicará dicha limitación si solo hubo una operación de compra en los dos meses anteriores y al inicio no se poseían homogéneos."
- Compras posteriores en 2m siguientes "también pueden determinar recompra" (sin fórmula proporcional explícita para posteriores).
- Imputación posterior solo ante "transmisión definitiva" = "en los dos meses anteriores o posteriores a ella, no se adquieran nuevamente homogéneos".
- Identificación: FIFO art. 37.2.

Conclusión: el `qty > 0` del código **coincide con AEAT 2025** (condición necesaria probada). No es mera importación IRS, aunque se parezca. La lectura ley-literal aislada ("basta adquirir") es incompleta sin este desarrollo. Matiz: `qty > 0` es necesario pero no suficiente para clonar AEAT (falta proporcionalidad `min(remanente, comprado previo)`, simetría posterior explícita, transmisión definitiva encadenada).

Contraste USA (para no confundir): SEC/IRS wash-sale = 30 días antes/después, "substantially identical", pérdida disallowed + ajuste de base. España = 2 meses / 1 año, "homogéneos" art. 8 RIRPF, diferimiento + declaración obligatoria + complementaria art. 73.2 RIRPF si la recompra es posterior al plazo declarativo. No citar IRS como fundamento.

## 4. Asturias: sin especialidad para este cálculo

- Hecho imponible, art. 33, cuantificación, FIFO e integración en base del ahorro (arts. 46/49): normativa estatal indisponible. CCAA solo pueden regular escala general, mínimo autonómico ±10% y deducciones en cuota autonómica con límites (art. 46 Ley 22/2009), sin minorar el gravamen de una categoría de renta ni tocar la base del ahorro.
- Deducciones Asturias Renta 2024 (26 rúbricas) y 2025 (27, se añade celíaca): ninguna afecta a venta de acciones cotizadas. La única con la palabra "acciones" es suscripción de nuevas entidades no cotizadas (art. 14 octodecies TR: 30%, límite 6.000 €/año, SA/SL asturiana activa, 1 empleado, <40% con parientes, mantener 3 años) — incompatible con wash-sale de cotizadas.
- Tipos base del ahorro para residente en Asturias = estatales supletorios arts. 66+76 (50% estatal + 50% autonómico). Asturias solo legisla escala general (2024: 10–25,5%; 2025 Ley 3/2025: 9–26% + mínimo +10%). Ahorro 2024 y 2025: 19/21/23/27 y 28% (>300k en 2024) / 30% (>300k en 2025). 2026 no verificable (sin Manual ni LP publicados y verificados).
- Declaración: apartado F2 Renta WEB (acciones negociadas, base del ahorro); la pérdida con recompra se consigna pero no se integra hasta transmisión definitiva. Nº de casilla vigente no verificado (los 368/369 que circulan son del modelo 2010 para IIC — no reutilizar).

## 5. Gaps del motor frente a lectura rigurosa (resumen auditoría)

Críticas (alterarían la declaración si el informe se usa literal): G1 sin ISIN/homogéneos (ticker ≠ valor; clases, splits, ADR, ETF distinto emisor); G2 sin flag cotizado (aplica 2m a todo; falta ventana 1 año no cotizadas); G3 fondos/IIC con régimen propio tratados como acciones; G4 cobertura solo-ledger (recompras en otro bróker/cuenta ignoradas → verde falso); G5 lectura `capacity/qty` como convención pineada pero con orden de absorción entre lotes no verificado en AEAT.
Medias: G6 lote exacto al que se difiere y orden entre ventas múltiples; G7 `over_sell` a coste cero sumado al total (cortos tienen régimen distinto); G8 sin arrastre/compensación 4 años ni tope 25% ahorro; G9 FX del bloqueo (FX venta original) vs FX de afloramiento; G10 `window_open` con `last_data_date` global y criterio deducir+avisar no respaldado; G11 `relativedelta(months=2)` vs cómputo civil de "dos meses" en bordes; G12 fees/FX/redondeo; G14 scrip/Modelo 720 no distinguidos (skips explícitos honestos). Baja/confusión: G13 bucket corto/largo 1 año ajeno a IRPF conviviendo en UI fiscal.

## 6. Dictamen

- Revertir fue prudente. Cambiar la compute en cualquier dirección sin cita (ampliar a "mera adquisición" o mantener "solo en cartera" como definitivo) mueve la base imponible sin fundamento.
- El informe hoy es **papel de trabajo orientativo para el asesor, no declaración**: FIFO trazable, `raw/blocked/computable` por venta, proporcionalidad, conservación económica, FX sin par y flags (`es-irpf-2m`, `window_open`, `missing_fx`, `over_sell`, `unattributed`) son valiosos, pero G1–G4 + G7/G8/G10 impiden "apto para declarar". Debe llevar disclaimer visible.

## 7. Plan de fix condicional (bloqueado hasta §8 + dictamen firmado)

1. Etiquetado condicional: `es-irpf-2m` solo con ISIN + flag cotizado; sin ellos, no bloquear con 2m — pérdida computable + `wash_sale_unknown` + motivo.
2. Ramas separadas: cotizada→2m; no cotizada→1a; IIC→régimen propio o `unsupported` explícito, jamás 2m por defecto.
3. Homogeneidad por ISIN, no ticker; tests con splits/clases/ETF.
4. Cobertura ledger: campo "recompras externas" + `coverage_incomplete` si el workspace no es la totalidad; disclaimer mientras tanto.
5. `window_open` honesta: doble referencia 31-dic del ejercicio + fecha de datos; criterio deducir-vs-excluir con cita; versionado del informe (recalcular con futuro no reescribe lo presentado).
6. `over_sell`/cortos, FX, carry: o con cita o como `blocking_limitation`.
7. Un test por cada ejemplo del Manual AEAT con BOE/DGT citados en el docstring; 720/scrip o implementados o `skip` con motivo, nunca verde falso.

## 8. Lo NO verificado (no usar como fundamento del fix)

1. Texto completo DGT (V0913-08, V3282-18, V1119-21, V0457-22, V2995-20, V0571-21...): Petete exige JS; solo excerpts. Lo que blogs afirman sobre ellas queda NO VERIFICADO.
2. Fórmula proporcional para compras POSTERIORES y orden de absorción entre lotes/ventas múltiples: inferido, no literal AEAT.
3. Cadenas venta-recompra-venta con ventanas solapadas: principio "definitiva" verificado, ejemplo numérico no.
4. Acciones USA (NYSE) como cotizadas UE MiFID a efectos 33.5.f: tesis de blogs (1 año) plausible pero sin cita AEAT/DGT abierta — NO VERIFICADO. Crítico para IBKR.
5. Cómputo "dos meses" (fecha a fecha vs meses naturales, inclusividad, febreros) y tipos 2026.
6. Casilla Renta WEB vigente para el flag de recompra.

## 9. Fuentes verificadas (abiertas con webfetch en la investigación)

- BOE Ley 35/2006 consolidada: `https://www.boe.es/buscar/act.php?id=BOE-A-2006-20764` (+ `&tn=0&p=20241224#a33` para redacción dic-2024).
- BOE RD 439/2007: `https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820` (art. 8 homogéneos).
- AEAT Manual 2025 cap. 11 (procedimiento decisivo): `https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/irpf-2025/c11-ganancias-perdidas-patrimoniales/ganancias-perdidas-patrimoniales-que-no-bi/perdidas-patrimoniales-que-no-se-tales.html` (actualizado 17/03/2026).
- AEAT Manual 2024 cap. 11 (misma ruta con `irpf-2024`, actualizado 10/04/2025; sin procedimiento).
- AEAT Cartera homogéneos: `https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-ayuda-presentacion/cartera-valores/2-valores-homogeneos.html`.
- AEAT integración diferida + complementaria art. 73.2: `.../manuales-ayuda-presentacion/irpf-2020/.../integracion-diferida-perdidas-patrimoniales-derivadas-transmisiones.html`.
- AEAT gravamen ahorro autonómico 2025: `.../irpf-2025/c15-calculo-impuesto-determinacion-cuotas-integras/gravamen-base-liquidable-ahorro/gravamen-autonomico.html`.
- AEAT deducciones Asturias 2024/2025: `.../irpf-2024-deducciones-autonomicas/guia-deducciones-autonomicas/principado-asturias.html` y `.../irpf-2025-deducciones-autonomicas/comunidad-autonoma-principado-asturias.html` (+ subpágina inversión nuevas entidades).
- BOE Ley 22/2009: `https://www.boe.es/buscar/act.php?id=BOE-A-2009-20375` (art. 46 competencial).
- Contraste USA: `https://www.sec.gov/answers/wash.htm`, `https://www.irs.gov/publications/p550`.
