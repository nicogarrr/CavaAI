# Presupuesto de tiempo para el modelo de respaldo

2026-10-16. Base: main `cfecb5f0139d0f7c30e459a256b5e24924103a2a`.

## Fallo reproducido

El adaptador tenía un `wait_for` de 45 s alrededor de primario + fallback. Si el
primario agotaba esos 45 s, la cancelación exterior no dejaba ejecutar el respaldo.
Un fallo rápido sí podía activar el respaldo. No era un cambio de proveedor ni de
claves: era una diferencia entre proveedor caído y proveedor lento.

## Cambio

Cuando hay un fallback **distinto del modelo resuelto** y existe límite total,
la ejecución del primario recibe como máximo 2/3 del límite. Incluye red,
reintentos y backoff. El último tercio queda disponible para el respaldo.
Con la configuración actual (45 s): primario como máximo 30 s, respaldo con aproximadamente
los 15 s restantes, sujeto al límite total original. Un fallo rápido del primario
permite al respaldo usar todo el tiempo restante, no solamente ese tercio.

- Sin fallback o si coincide con el modelo resuelto: presupuesto original intacto.
- Un primario que responde bien no llama al respaldo.
- La cancelación del cliente sigue propagándose y no dispara llamadas nuevas.
- El límite exterior sigue acotando la suma; un respaldo lento puede agotar el
  tiempo restante y devolver error. No se garantiza que el proveedor responda.
- El timeout del primario se registra en su traza y se conserva la metadata del
  fallback. Las respuestas de fallback siguen sin guardarse en la caché.
- Como antes, el plazo de generación no incluye operaciones de lectura/escritura
  de la caché que están fuera de ese bloque.

No cambia claves, modelos, proveedores, variables de entorno ni el total de 45 s.
No añade una cascada de proveedores ni habilita Gemini/OpenRouter.

## Pruebas aisladas

`tests/test_llm_fallback_budget.py` usa la factoría y adaptador reales con
`httpx.MockTransport`, sin llamadas de red ni gasto:

- Primario colgado: se cancela y el fallback responde consumiendo parte de su
  reserva (no una respuesta instantánea).
- El límite del primario también corta su backoff de reintentos.
- Ambos colgados: se inicia respaldo pero se conserva el error de timeout total.
- Sin respaldo o respaldo igual: el primario dispone de todo el plazo.
- Éxito del primario: no se llama al respaldo.
- Cancelación del caller: no se interpreta como fallo del primario.
- Fallo rápido: el respaldo puede usar más del tercio reservado.
- El coste de preparar la traza no desplaza el plazo absoluto del primario.

En la base exacta, los primeros siete canarios producen 3 fallos y 4 éxitos: el
respaldo no llega a ejecutarse en los tres casos de primario lento. Tras el cambio,
los nueve canarios pasan. Suite relacionada (proveedor, límites, router, cascada,
tool calling, logs/redacción y caché): **136/136**, exit 0. Ruff: exit 0.

```sh
cd data-engine
python -m pytest -o addopts= -q tests/test_llm_provider.py tests/test_llm_total_timeout.py tests/test_llm_fallback_budget.py tests/test_llm_cascade.py tests/test_llm_router.py tests/test_llm_tool_calling.py tests/test_llm_http_error_logging.py tests/test_llm_transport_diagnostics.py tests/test_response_cache.py
```

## Canario con respaldo real (10:20-10:21 CEST)

Proceso Python aislado usando el candidato y la configuración actual del backend:
se sustituye únicamente la respuesta del primario por una espera de 300 s en un
MockTransport. Esa espera se cancela por el nuevo plazo del primario; la petición
a `space-bunny-free` sí se envía al bridge real y responde `OK`.

Resultado: modelos intentados DeepSeek -> SpaceBunny, primario cancelado,
**33.054 s totales**, límite original **45 s**, respuesta de `space-bunny-free`.
Solo prompt neutro de salud, cache desactivada. No se simuló una caída en la API
real ni se cambió configuración/código cargado en los procesos de producción.
No demuestra que DeepSeek esté lento ahora: su lentitud fue inducida únicamente
en ese cliente de prueba. Muestra JSON adjunta en `llm-fallback-live-sample.json`.
