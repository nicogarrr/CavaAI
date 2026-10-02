# Corpus sintetico de evals de ingesta (C4)

`"origin": "synthetic_fixture"` — **todo este contenido es inventado**. Ninguna cifra,
CIK, accession, LEI, ticker ni nombre procede de un caso real, ni de una captura de
SEC / filings.xbrl.org / Financial Modeling Prep. Los numeros se eligieron para que
los fallos sean legibles a ojo (5.000.000.000 de ingresos, 500.000.000 de resultado,
4,25 de BPA) y no para parecerse a nadie.

Los ficheros JSON declaran el origen en la clave `"origin"`; los XML llevan un
comentario `<!-- origin: synthetic_fixture -->` en la cabecera. `tests/test_ingest_eval_fixtures.py`
falla si esa declaracion desaparece o si aparece un numero que no este en la lista
blanca de este README.

## Que se busca medir

Cuatro modos de fallo reales de la ingesta, con su fixture:

| Modo | Fixture |
|---|---|
| Variantes de periodo (FY / Q / TTM), `frame` con y sin, duraciones e instantaneos | `sec/companyfacts_quarterly.json`, `fmp/income_statement_history.json` |
| Cierre fiscal que no es el natural (junio, 52/53 semanas) | `sec/companyfacts_fiscal_june.json`, `sec/companyfacts_week52_drift.json` |
| Variantes de tag (`IncludingAssessedTax`, `ExcludingAssessedTax`, `RegulatedAndUnregulated`, `SalesRevenueNet`) | `sec/companyfacts_tag_variants.json` |
| Tags duplicados / re-expresado (10-K/A) | `sec/companyfacts_amended.json`, `sec/companyfacts_tag_variants.json` |
| Unidades incoherentes (revenue en EUR, BPA en USD) | `sec/companyfacts_units_mismatch.json` |
| XBRL con dimensiones de segmento / por clases | `sec/instances/*.xml` |
| `iXBRL` con y sin `unitRef`, `scale="3"`, `sign="-"`, `decimals` | `sec/instances/no_unitref_scale_sign.xml` |
| Filing amended, accession sin indice, filing duplicado, sin `primaryDocument` | `sec/submissions_amended.json`, `sec/index/*.json`, `sec/submissions_duplicate_filings.json`, `sec/submissions_no_primary_document.json` |
| Look-ahead (`FY2999`) anclado y sin ancla | `sec/companyfacts_lookahead.json` con `sec/submissions_lookahead.json` / `sec/submissions_lookahead_unanchored.json` |
| FMP con `date` como epoch y como ISO | `fmp/income_statement_epoch.json`, `fmp/income_statement_history.json` |
| FMP con `limit`/`symbol` incoherentes | `fmp/income_statement_foreign_symbol.json` |
| FMP con ratios `null` / cadena vacia | `fmp/ratios_nulls.json` |
| ESEF con y sin `unitRef`, con `scale` 3/6, `sign="-"`, `decimals` | `esef/xbrl_json_no_unitref.json`, `esef/xbrl_json_signed_decimals.json` |
| ESEF con taxonomia ES de extension frente a IFRS | `esef/xbrl_json_es_taxonomy.json` |
| ESEF sin etiquetar (degradacion honesta) | `esef/untagged_report.json` |

## Numeros que este README declara

Todo numero del corpus esta en la lista blanca de `ALLOWED_VALUES` en
`tests/test_ingest_eval_fixtures.py`, que tambien comprueba que no aparece ningun
otro valor monetario. Los que se usan como "unexpectedos" en controles negativos
(`999000000000`, `888000000000`, `99000000000`) estan declarados aqui como
deliberadamente ajenos al emisor:

- `999000000000` / `888000000000` — filas de `fmp/income_statement_foreign_symbol.json`
  que pertenecen a OTRO emisor (`symbol: "OTRA"`).
- `99000000000` — hecho de balance con accession que submissions no lista
  (`sec/companyfacts_lookahead.json`).
- `42000000000` / `21000000000` — ingresos de FY2999 / FY2998 del caso de look-ahead.