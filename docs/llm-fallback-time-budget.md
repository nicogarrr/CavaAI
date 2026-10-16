# Respaldo tardío sin cortar una respuesta primaria válida

2026-10-16. Base: main `cfecb5f0139d0f7c30e459a256b5e24924103a2a`.

## Fallo y revisión del auditor

El adaptador tenía un límite total de 45 s alrededor de primario + fallback. Si el
primario consumía esos 45 s, el respaldo no llegaba a ejecutarse. Un rechazo rápido
sí permitía probar el respaldo.

La primera propuesta cancelaba al primario a los 30 s para reservar 15 s al
respaldo. El auditor encontró una regresión real: primario válido a los 36 s y
respaldo con 403 daba error, cuando antes habría devuelto el primario. Se descarta
ese diseño y se sustituye por ejecución solapada tardía, sin cortar el primario.

## Comportamiento actual de esta PR

Si hay un respaldo distinto del modelo resuelto:

1. Arranca el primario normalmente, con sus retries/backoff.
2. Si responde bien antes de 2/3 del plazo, termina sin llamar al respaldo.
3. Si falla antes, arranca el respaldo inmediatamente (como antes).
4. Si sigue pendiente a los 2/3, arranca el respaldo **en paralelo**. El primario
   original sigue ejecutándose, sin cancelación ni reinicio.
5. La primera respuesta válida gana. Un fallo de cualquiera no corta la espera del
   otro. Si ambos acaban a la vez, se prefiere el primario válido.
6. Al ganar uno, cancelar/recoger el otro. Si cancela el caller o se agota el total,
   cancelar/recoger ambos. No se dejan tareas de generación sueltas.

Con los 45 s actuales, el respaldo se inicia aproximadamente a los 30 s si el
primario sigue pendiente, con unos 15 s restantes. El primario conserva hasta el
final su posibilidad original de responder. Si el respaldo falla a los 31 s y
el primario responde a los 36 s, se devuelve el primario, sin reiniciarlo.

Sin respaldo útil no se altera el primario. El límite total de generación sigue
siendo 45 s. Como antes, la lectura/escritura de caché queda fuera de ese bloque.
La respuesta del respaldo sigue sin cachearse. Las trazas distinguen primario
lento (`fallback_trigger=primary_slow`) de error primario real.

### Coste operativo y límites

No cambia claves, modelos, proveedores, variables de entorno ni total configurado.
Puede haber **dos peticiones concurrentes** durante la última parte del plazo,
solo si el primario sigue pendiente. Usa más capacidad/cuota que esperar solo al
primario; cancelar la tarea local no garantiza que el servidor remoto interrumpa
su cómputo. No se promete ausencia de consumo remoto ni respuesta garantizada.
La configuración actual usa los modelos gratuitos verificados de OpenCode.

Se conserva el canario de respuesta primaria válida dentro del plazo. No se hace
la afirmación universal de que toda carga externa será más rápida o idéntica:
la latencia y capacidad reales de los proveedores quedan fuera del control local.

## Pruebas aisladas

`tests/test_llm_fallback_budget.py` usa factoría/adaptador reales y MockTransport,
sin llamadas de red. Once canarios cubren primario lento con respaldo válido,
backoff, ambos colgados, sin respaldo, respaldo idéntico, éxito temprano,
cancelación antes/después de arrancar respaldo, fallo rápido, primario válido
entre 2/3 y el final con backup403 y con backup colgado.

El canario del auditor, escalado a 0.3 s total y primario válido a 0.25 s con
backup403, devuelve el primario original sin cancelación ni reinicio. El diseño
anterior lo cancelaba a 0.2 s. Los primeros siete canarios contra base exacta
reprodujeron tres fallos (nunca llegaba al respaldo); el candidato revisado pasa
los once. Suite relacionada: **138/138**, exit 0. Ruff: exit 0.

```sh
cd data-engine
python -m pytest -o addopts= -q tests/test_llm_provider.py tests/test_llm_total_timeout.py tests/test_llm_fallback_budget.py tests/test_llm_cascade.py tests/test_llm_router.py tests/test_llm_tool_calling.py tests/test_llm_http_error_logging.py tests/test_llm_transport_diagnostics.py tests/test_response_cache.py
```

## Canario con respaldo real

Proceso Python aislado, usando este candidato y configuración actual del backend.
Solo el primario se sustituye por una espera de 300 s en MockTransport. SpaceBunny
sí recibe el prompt neutro de salud a través del bridge real y responde. El
primario se cancela **después del éxito del respaldo**, no al activar el respaldo.
No se modifican procesos ni configuración de la API real. Cache desactivada.
Resultado y tiempo total en `llm-fallback-live-sample.json`. La lentitud primaria
es inducida solo en ese cliente; no demuestra que DeepSeek esté lento ahora.
