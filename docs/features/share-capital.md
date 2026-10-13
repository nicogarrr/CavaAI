# Dilución y recompras

- Ruta: `/research/[ticker]/share-capital`, dentro de Financieros.
- Lectura: `GET /api/companies/{ticker}/share-capital`; requiere la misma identidad firmada y sesión de tenant que el resto del research.
- Actualizar SEC usa la ingesta existente, sin proveedores nuevos ni claves adicionales.

## Datos y límites

La serie usa exclusivamente `shares_outstanding` reportado, en unidades `shares`, con documento y URL HTTPS. No sustituye saldos por `shares_diluted`: el promedio ponderado no es un saldo. Selecciona el último fact almacenado por fecha y excluye fechas futuras, saldos no positivos, semillas y estimaciones.

Los flujos anuales usan conceptos SEC separados:

| Métrica | Concepto | Unidad |
| --- | --- | --- |
| Recompras | PaymentsForRepurchaseOfCommonStock | USD |
| Emisiones | ProceedsFromIssuanceOfCommonStock | USD |
| Acciones recompradas | StockRepurchasedDuringPeriodShares | shares |
| Compensación en acciones | ShareBasedCompensation | USD |

Los flujos nuevos requieren `start`, duración anual y ancla de filing mediante el validador existente. Nunca se suman FY y trimestres/YTD. La cifra ausente se devuelve como campo ausente, no cero. Cero reportado es válido para los flujos.

La variación neta es un derivado entre dos saldos y no prueba emisiones/recompras: puede incluir compensación, conversiones, splits o cambios de clase. Si existe un split registrado entre las fechas se suprime el cambio. Los saldos y el gráfico permanecen sin ajustar; no se afirma cobertura completa de splits.

La ingesta añade `capital_fact_provenance` al documento SEC con concepto y fecha `filed` de cada periodo. Datos anteriores a esta feature conservan fecha del saldo y enlace a la fuente, pero no inventan una fecha individual de presentación; `source_updated_on` es la fecha global del documento, no la fecha de ese fact. Una nueva actualización SEC incorpora los metadatos individuales.

UI: gráfico, saldos y flujos anuales en tabs, tablas de diez filas, navegación superior e inferior, USD compactos en formato inglés. Las tablas anchas permiten desplazamiento horizontal en móvil.

## Verificación

`tests/test_share_capital_service.py` cubre distinción entre saldos/promedios, cero vs ausencia, filas no verificadas, splits, restatements, aislamiento tenant, conceptos SEC y una ingesta de extremo a extremo con rechazo de flujos instantáneos/trimestrales etiquetados FY.

La vista se inspeccionó en Chrome con fixtures locales a tamaños desktop y 390px. Ningún fixture ni ruta de preview se incorpora al producto.
