# Escenarios por accion (item 7)

`GET /api/companies/{ticker}/thesis-scenarios` lee la ultima version
`thesis_5y` del usuario. Es una vista del snapshot guardado, no una nueva
valoracion. No escribe, recalcula, llama al LLM, usa proveedores de pago ni
consume la cuota diaria. No necesita migraciones, paquetes nuevos ni frontend.

## Contrato

- `fuente` identifica modelo, version y fecha de corte.
- `escenarios.bear/base/bull` contiene nombre en espanol y proyecciones por
  ejercicio. `ingresos`, `fcf`, `bps` son objetos con `valor`, `etiqueta`,
  `fuente` (tabla, modelo, fila), `fecha`, `fuentes_base`, `metodo` y `motivo`.
- Las cifras publicadas son INFERIDO: incluso con anclas OFICIALES, una
  proyeccion no es un dato oficial. N/D tiene valor null y motivo explicito.
  Identificadores, versiones y ejercicios son metadata, no estimaciones.
- La tabla aporta los numeros; la traza de la misma version aporta su linaje.
  Una discrepancia mayor que la precision Numeric de la columna bloquea la
  cifra. Nunca se rellena un hueco con cero o una version anterior.
- Un snapshot incompleto puede mostrar los campos validos y bloquear otros.
  `estado=persistido` solo afirma que existe una version compatible con filas,
  no que todos los campos sean publicables. Hay que mirar cada etiqueta.
- No se presentan probabilidades, retornos ni precio actual, ni se ordenan o
  recortan los escenarios para que parezcan coherentes. Se conserva el aviso
  de coherencia del productor. No se asume una divisa nueva.

## Regla de ausencia de cifras LLM

El productor v1 permite InferredInput (origen LLM por defecto), drivers del
modelo y asunciones sin linaje oficial. Este lector no los publica.

Solo acepta crecimiento OFICIAL con URL y fecha no posterior al corte.
El CAGR v1 no conserva la procedencia de sus extremos historicos: queda N/D,
aunque el ultimo ancla sea oficial y el metodo tenga un prefijo determinista.
Incluso historia realmente oficial queda bloqueada sin ese linaje persistido.
No se reconstruye desde facts actuales, que pueden haber cambiado desde el
snapshot. Para habilitar CAGR, el productor debe guardar la procedencia de
cada extremo y su cadena de calculo; una etiqueta o un prefijo no bastan.
El margen FCF puede ser derivado de las dos anclas oficiales del snapshot,
o una tasa OFICIAL con URL y fecha, bajo el contrato v1 existente.
Las anclas deben ser OFICIALES con URL y fecha. La cadena de crecimiento debe
estar completa y acreditada hasta cada ejercicio. FCF exige anclas del mismo
periodo; BPS exige resultado neto y acciones oficiales.

El precio objetivo queda N/D: la traza v1 no conserva el origen completo de
los inputs del motor de valoracion. Mostrarlo no cumpliria la regla de cero
cifras LLM. Para habilitarlo en el futuro, el productor debe persistir el
linaje determinista del motor, no basta anadir una etiqueta en este lector.
Esto puede producir muchas salidas N/D en tesis antiguas. Se prefiere un
bloqueo honesto a declarar de prestado un origen no LLM.

No verifica fuentes por red en cada GET: usa la procedencia guardada por
thesis_projection_service v1. El contrato textual de metodos v1 se valida
por prefijos conocidos solo para margen FCF (con ambas anclas oficiales),
nunca para CAGR; no se considera prueba para una version futura. Un cambio del productor requiere revisar este lector.

## Pruebas

`cd data-engine && python -m pytest tests/test_thesis_scenarios.py tests/test_thesis_projection.py`

Cubren solo SELECT, ausencia de recalculo/autoflush, cifras y procedencia,
bloqueo LLM, cadena acumulada, traza divergente, fechas, tenant, snapshots
vacios o incompatibles y errores HTTP en espanol.
