# LLM: diagnóstico de bridge y serve aislados

## Evidencia real

Todo en una red Docker propia, bridge y serve propios, sin usar chat, sesión ni datos de Nico. OpenCode1.19.1 copiado del binario existente, credencial existente de lectura, sin cuentas nuevas ni llamadas a modelos de pago. El catálogo servido declara coste0 para los modelos con sufijo-free usados.

- Bridge anterior: DeepSeekV4.1FlashFree60.307sHTTP502timeout; space-bunny-free60.081sHTTP502timeout.
- Logs del serve aislado: ambos modelos reciben Rate limit exceeded en aproximadamente0.7s; la llamada síncrona no lo devuelve al bridge y sigue esperando. No se afirma alcance cuenta/IP/modelo del límite.
- Cada sesión sin título disparaba además una llamada DeepSeek para titular, que también reintentaba3veces y fallaba con ratelimit. Se frenó la batería al confirmarlo, sin ejecutar MiMo en esa batería; se abortó la sesión Nemotron pendiente.
- Health y listado del serve respondían~0.1s con0tokens mientras la respuesta de modelo seguía pendiente. No hay evidencia de caída HTTP del serve; no se recomienda reiniciar a ciegas.
- Canario Nemotron3.5LightningFree con bridge async y título fijo:41.067s, timeout40s, cancelación observada en logs, sin respuesta utilizable. No se declara sustituto fiable.
- Canario MiMo y resultado final: cuerpo del PR.

## Cambio propuesto

Usar prompt_async (204sinJSON), consultar estado de sesión, propagar429 al primer retry por cuota/ratelimit, título fijo que evita la llamada extra, abort+delete con2s cada uno. No acumular el mismo texto entre polls. Deadline monotónico30s con peticiones individuales10s, inferior al timeout de chat45s en el caso normal; una petición final y limpieza pueden sumar tiempo y se declaran como límite. Sin cambiar modelo de producción todavía.

## Pruebas

4canarios offline: respuesta async sin duplicados, cuota inmediata sin reintentar, error de proveedor y timeout con abort/cleanup. Ruff dirigido con configuración del repo verde. No prueban calidad de modelo ni recuperación de cuota. API/HTTP real aislado se registra arriba.

## Límites

No se ha afirmado que el chat de producción esté reparado ni que cambiar modelo sea suficiente. No se usa una clave de pago ni se crea cuenta. No hay datos oficiales inventados. La cuota del servicio gratuito puede seguir limitando todas las opciones.
