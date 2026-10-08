# Alertas salientes por el bot de Asistenta

Sin API de pago. CavaAI usa `sendMessage` de Telegram Bot API y el bot ya
existente de Asistenta, sin crear otro bot ni consumir `getUpdates`.
Asistenta sigue siendo el único consumidor de actualizaciones/webhook.

## Configuración y contrato

1. Configurar `TELEGRAM_BOT_TOKEN` en el entorno privado del backend y worker
   con el token del bot de Asistenta. Nunca guardarlo en Git, frontend o logs.
2. `TELEGRAM_ENABLED=true` habilita el adaptador, pero **no** crea suscripciones.
3. Asistenta debe obtener `message.chat.id` de una conversación privada iniciada
   por el usuario y verificar su asociación con la identidad autenticada de
   CavaAI. No confiar en un chat reenviado ni permitir grupos para esta conexión.
4. El propietario confirma el chat y los tipos deseados desde la sesión firmada
   de CavaAI. La API no permite que otro usuario modifique la suscripción del
   propietario. El chat positivo privado se guarda por workspace personal/tipo;
   nunca se reutiliza `TELEGRAM_CHAT_ID` global para estos eventos.
5. `PUT /api/alerts/telegram-subscriptions/{event_type}`:
   `{ "enabled": true, "chat_id": "<chat privado confirmado>" }`.
   Tipos: `thesis_broken`, `new_filing`, `insiders`, `shorts_rising`.
   `GET /api/alerts/telegram-subscriptions` devuelve los cuatro tipos, apagados
   por defecto. Desactivar usa el mismo PUT con `enabled:false`.
   Este PR ofrece la API, no una pantalla nueva ni un flujo de vinculación
   automático. Hasta verificar el chat y activar cada tipo no se envía nada.

Una suscripción requiere tenant y usuario verificados por el puente de auth
existente, nunca IDs suministrados en el cuerpo. El modelo actual de CavaAI es
un workspace personal de un propietario; no es un servicio multiusuario dentro
del mismo workspace. Para añadir miembros se necesitaría un outbox por destinatario.

## Eventos y datos

- Tesis: `claim_contradicted`/`thesis_broken` persistidos; no se afirma que una
  inferencia del LLM sea un hecho. Una contradicción pide revisión, no vender.
- Filing: documento SEC/CNMV oficial de empresa en cartera/seguimiento. Se avisa
  aunque aún falte texto o informe comparable; se dice que el análisis puede
  estar pendiente/sin datos. Una misma fuente/checksum no crea dos avisos.
- Insiders: señales persistidas Form 4, con huella de transacción y versión de
  regla. Se elimina el envío directo sin outbox del evaluador insider.
- Cortos: subida de posiciones FINRA respecto al periodo anterior (fecha válida
  y <=35 días) o aumento de suma pública CNMV con los mismos titulares entre
  consultas. La suma CNMV es parcial. El volumen corto diario FINRA nunca se
  interpreta como posición abierta ni sentimiento bajista.

Se leen eventos existentes; el barrido no descarga fuentes ni llama al LLM.
La actualización de cortos consulta FINRA pública además de volumen diario.
El reconciliador existente se ejecuta cada 10 minutos por tenant en Dramatiq,
con lease Redis. Recoge alertas nuevas de emisores que solo escriben a DB.
Los emisores que ya llaman `dispatch` pueden enviar sin esperar al barrido.
No se reproduce historial anterior a la activación/re-activación/cambio de chat.

## Deduplicación, fallos y revocación

Huella de evento en `research_alerts` y UNIQUE `(alert_id, channel)` en
`alert_deliveries`. Claim SQL atómico antes del HTTP evita dobles envíos por
workers concurrentes. Se revalida consentimiento en cada intento, incluidas
reconciliaciones. Rechazo permanente 4xx no se reintenta; 429 honra el enfriamiento
hasta una hora; timeout/5xx es `unknown`, no éxito, y espera al TTL de diez minutos.
Telegram no ofrece clave de idempotencia: tras resultado ambiguo puede repetirse
un aviso. No se promete exactly-once. Desactivar no puede retirar un HTTP que
ya salió antes de la revocación. Solo HTTP exitoso **y** `ok:true` es entregado.
Los errores persistidos omiten token, URL del bot, contenido y respuesta cruda.

## Despliegue

Aplicar Alembic hasta `0051_alert_subscriptions`, reconstruir backend/worker/
scheduler con `docker-compose.prod.yml`. Las variables de entorno de Telegram
ya existen. No se activa nada con la migración y no se toca `wake.ts`.
Comprobar primero con un chat privado de prueba y consentimiento explícito;
este PR usa HTTP simulado y no envía mensajes reales ni guarda credenciales.
