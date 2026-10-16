# LLM: diagnóstico de bridge y serve aislados

## Evidencia real

Todo en una red Docker propia, bridge y serve propios, sin usar chat, sesión ni datos de Nico. OpenCode1.19.1 copiado del binario existente, credencial existente de lectura, sin cuentas nuevas ni llamadas a modelos de pago. El catálogo servido declara coste0 para los modelos con sufijo-free usados.

- Bridge anterior: DeepSeekV4.1FlashFree60.307sHTTP502timeout; space-bunny-free60.081sHTTP502timeout.
- Logs del serve aislado: ambos modelos reciben Rate limit exceeded en aproximadamente0.7s; la llamada síncrona no lo devuelve al bridge y sigue esperando. No se afirma alcance cuenta/IP/modelo del límite.
- Cada sesión sin título disparaba además una llamada DeepSeek para titular, que también reintentaba3veces y fallaba con ratelimit. Se frenó la batería al confirmarlo, sin ejecutar MiMo en esa batería; se abortó la sesión Nemotron pendiente.
- Health y listado del serve respondían~0.1s con0tokens mientras la respuesta de modelo seguía pendiente. No hay evidencia de caída HTTP del serve; no se recomienda reiniciar a ciegas.
- Canario Nemotron3.5LightningFree con bridge async y título fijo:41.067s, timeout40s, cancelación observada en logs, sin respuesta utilizable. No se declara sustituto fiable.
- MiMo30.408s timeout con el prototipo de30s; logRateLimit en~0.7s, pero /session/status NO lo expuso temprano. No se demostró429rápido.

## Alcance revisado tras auditoría

Solo transporte prompt_async (204sinJSON), título fijo que evita otra llamada y no acumular texto entre polls; abort+delete de2s porpetición. Se elimina la captura temprana de429 porque no se demostró con el serve actual. Se preservan TIMEOUT_S150 y requesttimeout60 originales: no se trunca una primaria válida de35-44s. El contador usa monotonic; NO constituye un deadlineabsoluto porque creación, peticiones de red y cleanup pueden sumar. No se presenta como arreglo de latencia o disponibilidad.

## Pruebas

4canariosoffline: async204sin duplicados, primaria válida a44s, error de proveedor y agotamiento del contador150s conabort/cleanup. Ruff dirigido con configuraciónrealrepo. No prueban deadlineabsoluto ni calidad ni recuperación de cuota.

## Límites

Sin despliegue de producción. No se ha demostrado unmodelo gratis fiable ni que reiniciar serve corrija la cuota. El prototipo30s se retiró porque degradaba primariasválidas. El código429temprano se retiró porque el estado delSDK no lo expuso enelcanarioreal. Este PR reduce trabajoextra y cambia transporte, no promete reparación delchat. No cuentas ni claves de pago nuevas.
