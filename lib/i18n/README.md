# i18n mínima (es-ES)

## Añadir una clave

1. Añade el texto (el español que ya existe en el código) a `es.json` bajo el
   namespace que toque: `common.*`, `nav`, `ui.*`, o el del módulo
   (`portfolio.*`, `screener`, `propicks`, `insider`, `taxes`, `plan`, ...).
2. Sustituye el literal por `t('namespace.clave')`. Con variables:
   `t('portfolio.fxMissingNotice', { n: 2 })` y `{n}` en el valor de `es.json`.
3. Regla de entrada: **solo** claves que aparecen en 2+ sitios o en estados
   críticos (vacío / error / cargando / label de tabla). El resto sigue siendo
   un literal en su componente: un diccionario de 400 claves no se mantiene.

`TranslationKey` se deriva de `typeof es`, así que una clave mal escrita no
compila. En desarrollo `t()` **lanza** si la clave o una variable no existen
(para que no salga `{n}` en pantalla ni un "N/D" silencioso); en producción
devuelve la clave.

## Por qué no next-intl

La app es íntegramente es-ES: no hay enrutado por locale ni idiomas
paralelos. next-intl aporta middleware, carga de mensajes por request y un
provider de cliente que aquí no se usan. `es.json` + `t()` da lo único que
hace falta (teclado, error temprano) sin dependencia ni bundle extra.

## Qué NO traducir

- **Anglicismos aceptados** (son el vocabulario del producto): Watchlist,
  Screeners, Screener, ProPicks, Research OS, Movers, Sharpe, Sortino,
  Drawdown, CAGR, PER (TTM), Market Cap, IBKR, EDGAR, Monte Carlo,
  walk-forward, backtest, Ticker.
- **Claves de datos del backend**: `LIMITATION_LABELS` en
  `app/(root)/ownership/page.tsx` usa la frase inglesa como clave y el español
  como valor (documentado en un comentario del propio archivo).
- `console.error`/`console.warn`, nombres de variables, `defaultValue="en"`
  del input de knowledge (es el idioma del documento que se ingesta, no copy).
