# Respaldo gratuito de chat: Groq GPT-OSS 120B

## Cuenta y privacidad verificadas el 16 de octubre de 2026

- Plan actual Free, $0, sin añadir tarjeta: https://console.groq.com/settings/billing/plans .
- Global ZDR activado y confirmado en la cuenta: https://console.groq.com/settings/data-controls . Esto activa ZDR de inferencia y desactiva batch y fine-tuning que almacenan datos. Todos los clientes pueden activar ZDR según https://console.groq.com/docs/your-data .
- Límites reales de la cuenta para `openai/gpt-oss-120b`: 30 peticiones/minuto, 1.000/día, 8.000 tokens/minuto y 200.000/día. https://console.groq.com/settings/limits y https://console.groq.com/docs/rate-limits . Si se agotan, se degrada honestamente; no se cambia de plan.
- Modelo de producción, distinto de DeepSeek V4.1 Flash: https://console.groq.com/docs/models . No se afirma equivalencia de calidad.
- Groq no puede entrenar con inputs/outputs sin permiso. Sus términos §4.3 excluyen asesoramiento financiero profesional: https://console.groq.com/docs/legal/services-agreement/ . El respaldo recibe una instrucción adicional de limitarse a explicación y análisis factual educativo, sin recomendaciones personalizadas de compra, venta o asignación.

La clave está guardada en la bóveda y en Bitwarden, organización y colección Asistenta. No hay secretos en el repositorio. El acceso a Groq usa enlace al correo, no una contraseña nueva. La verificación de Free y ZDR es operativa, no una consulta automática de esos ajustes en cada petición. No debe activarse un plan de pago ni desactivarse ZDR mientras se use esta configuración.

## Alcance

Solo `ChatService` usa este respaldo. Los jobs, tesis y demás consumidores de la fábrica LLM original no cambian. La opción está apagada por defecto. Exige clave y confirmaciones explícitas del plan gratuito y ZDR. Endpoint y modelo Groq son fijos; no hay una URL o modelo de pago configurable por este camino. El primario también debe resolver a un modelo verificado gratis antes de tocar la red.

El primario conserva el plazo total original (45 s en producción). Se lanza el respaldo tras 25 s, o al fallar antes el primario. Una respuesta primaria válida todavía puede ganar. Se cancelan y recogen las tareas perdedoras. Groq no tiene reintentos, usa effort `low`, timeout de petición 12 s y total 15 s. Nunca recibe el effort `max` de DeepSeek. Una respuesta truncada o degradada no gana.

El router declara una ruta compuesta real, no finge ser el modelo gratis primario. No se amplía la allowlist global ni se eluden sus guardas. El chat general informa del modelo y proveedor que respondieron. La estimación interna de coste no es la factura real; se conserva como estimación y no se presenta como un cargo del plan Free.

## Pruebas

44 pruebas dirigidas pasan, con Ruff limpio: primario rápido sin respaldo, 429, primario lento aún válido, respaldo rápido, ambos lentos, cancelación externa, error propio sin redispatch, tarea ajena y tools fuera del respaldo, salida truncada, límite de asesoramiento y validación fail-closed de configuración. Incluye el adaptador HTTP real con transporte simulado y el sobre correcto de modelo, effort y User-Agent.

Pruebas reales desde la VM, solo con preguntas genéricas y datos sintéticos, sin cuenta/sesión/cartera de Nico y sin tráfico a OpenCode:

- API directa: 4/4 HTTP 200. PER 1,946 s (truncado por el límite deliberado de 700 tokens, no se considera respuesta completa), escenario sintético 1,542 s con pesos 60/40 y caída total 6% correctos, ausencia de datos actuales 0,370 s sin cifra inventada e inyección documental 0,568 s sin falsa atribución CNMV.
- Prompt real del chat general y adaptador: 0,697 s y 0,592 s, respuesta española completa.
- Prompt estructurado real y adaptador: 1,518 s, JSON y citas válidos. Fixture `financial_fact:1` claramente marcado como sintético y no oficial. El primer intento usaba tipo de fuente `synthetic`, que el guard rechazó correctamente. Cambió el fixture, no la guarda. Es una comprobación básica del contrato, no una prueba de calidad exhaustiva ni del rendimiento con una cartera grande.

El primario de estas pruebas se simula con HTTP 429 en `primary.invalid`; nunca se llamó a OpenCode. Groq recibió únicamente ejemplos de prueba. Sin User-Agent, urllib obtuvo 403; con `cavaai/1.0`, catálogo y chat respondieron 200. Ese encabezado está incluido.

## Límites y despliegue

No se ha activado en producción. La cuota de 8K tokens/minuto puede ser insuficiente para prompts largos o varias pestañas; un gran contexto de 131K del modelo no equivale a esa cuota. No se garantiza SLA ni capacidad ilimitada. La segunda llamada del guard de salida también consume cuota. La cancelación local no prueba que el proveedor haya detenido todo cómputo remoto.

La activación exige PR auditado, SHA exacto autorizado, CI verde, copia de configuración e imagen anteriores, verificación de Free/ZDR y una prueba acotada sin datos de Nico. Rollback: desactivar `GROQ_CHAT_FALLBACK_ENABLED` y volver a la imagen/configuración anterior. No se promete que esto resuelva todos los modos ni la disponibilidad de OpenCode.
