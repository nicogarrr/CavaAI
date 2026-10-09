# Narrativa de tesis basada en noticias (item 8)

Al generar una nueva versión de tesis, `narrative_sections` contiene prosa redactada
por el modelo en español, no fragmentos seleccionados. El Markdown guardado incluye
el mismo análisis. El resumen ejecutivo y la valoración siguen siendo deterministas.

- Activación: `THESIS_NARRATIVE_LLM_ENABLED=1` y proveedor configurado habilitado.
- Se usa el router configurado para `main_financial_analysis`. Solo modelos gratuitos
  verificados y fallback gratuito; configuración no verificable bloquea la llamada.
- Entrada: snapshot de noticias persistidas de NewsEvent de la empresa, máximo ocho,
  con fecha registrada dentro de los últimos catorce días. Sin scraping ni scheduler.
- Se distingue titular original de resumen del pipeline. Fechas y enlaces se conservan.
- Cada sección exige ids de noticias recibidas. La prosa del LLM no puede contener
  ninguna cifra numérica, cantidad en palabras, porcentaje ni URL, aunque esté en la
  entrada. Evita reasignar cifras reales a otra métrica. El código añade aparte los
  titulares completos, fechas y enlaces como citas literales; no calcula ni reescribe
  sus cifras. No hay excepción que permita números dentro de URLs del modelo.
- Idioma y texto corrupto pasan por `complete_guarded`. Se reutiliza el reintento
  transitorio de propuestas LLM; no se cambia de modelo por fallos del upstream.
- Todo análisis aparece marcado INFERIDO. Las citas las añade el código, no el modelo.
- Proveedor caído, JSON vacío/roto, evidencia ausente, salida inválida, presupuesto
  agotado o modelo de pago: `Sin datos`. No se inventa una narrativa de sustitución.
- La lectura y presupuesto usan sesiones cortas cerradas antes de red. La narrativa
  se prepara ANTES del savepoint de tesis y solo circulan escalares por el puente
  asíncrono. Un timeout de corrutina cancela la red a los sesenta segundos.
- Si el llamador ya tiene transacción activa, no se cambia su trabajo: Sin datos,
  sin llamada LLM. No se hace commit/rollback de su transacción para liberar locks.
- Cada respuesta recibida registra tokens (incluidas salidas rechazadas) con coste
  EUR 0, después de red en sesiones propias cortas. El guardado atómico de datos de
  tesis no tiene commits parciales por la narrativa. El registro de consumo sí es
  independiente y puede existir aunque luego falle el guardado de la tesis.

Las versiones ya guardadas no se reescriben. Para probar con evidencia sin cambios,
generar una nueva versión explícitamente (`force_new_version=True`).

El validador separa cifras y enlaces de la prosa del LLM, no garantiza la veracidad de
las noticias ni la corrección económica de las inferencias. La etiqueta INFERIDO
no convierte la salida en un hecho verificado.

## Pruebas herméticas

`pytest tests/test_thesis_news_narrative.py tests/test_thesis_narrative_llm.py
 tests/test_llm_proposal_runner.py tests/test_llm_proposal_service.py
 tests/test_llm_output_guard.py`

No requieren llamada al proveedor ni credenciales reales.
