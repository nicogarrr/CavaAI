# Groq: respaldo opt-in del chat con contexto

## Decisión del propietario y límites

Nico decidió el 16oct2026 a las13:36:03 por WhatsApp "Responda tambien", después de que se le indicara que Groq recibiría datos suyos fuera del servidor con ZDR y que sus términos excluyen asesoramiento financiero. La pregunta anterior explicaba "chat general con tus datos" y el aviso previo explicitaba cartera/tesis. Main concretó general y ruta estructurada con contexto en PR aparte. Esto permite preparar el respaldo descrito, no saltar auditoría/CI/autorización de despliegue. Las definiciones locales de #1091 permanecen en PR separado y no se sustituyen.

## Transferencia exacta cuando se usa el respaldo

- General: prompt de sistema del chat general, pregunta original (incluido cualquier dato que contenga), clasificación de alcance, fecha UTC de revisión y bandera sources_available=false. No se añade historial ni cartera desde la base de datos a esta ruta.
- Estructurada: prompt de sistema del contrato de síntesis, pregunta original, ticker, IDs de fuentes permitidas, todas las secciones deterministas y hasta40fuentes recuperadas. Cada fuente se serializa tal como la recibe el servicio: puede incluir extractos/texto, títulos, URLs, IDs y otros campos. Según lo recuperado puede contener datos privados de cartera, memorias, tesis o documentos. ZDR NO evita esta transferencia. No se afirma que se envíe toda la cuenta o la base de datos completa.
- También se transmite el esquema JSON del contrato cuando corresponde, parámetros de generación y la instrucción educativa adicional. Credencial y metadatos técnicos normales de API (IP del servidor/encabezados/tiempos). La metadata interna de trazas no se añade como un mensaje nuevo.

No se publica texto generado sin las guardas existentes de contrato/citas/idioma. Se añade instrucción de análisis factual educativo sin recomendaciones personalizadas de compra/venta/asignación. Un filtro determinista rechaza patrones de recomendación y verbos de acción financiera; cubre los dos canarios conocidos de comprar/vender y adquiera/liquide. NO es una garantía semántica: puede omitir consejos expresados de otra manera y rechazar explicaciones inocuas. No se afirma "las recomendaciones no salen".

## Términos, privacidad, precio

Groq §4.3 excluye uso para consejo financiero profesional. El uso factual educativo y estas guardas reducen el riesgo pero no garantizan aceptación del proveedor. Groq podría suspender la cuenta o servicio; aceptar esta transferencia no elimina el límite contractual. Cuenta actual Free$0 sin tarjeta, GlobalZDR activado y comprobado en pantalla. No se permite upgrade, tarjeta ni plan pagado. Clave en bóveda y Bitwarden organización/colecciónAsistenta, nunca repo. ConfirmacionesFree/ZDR son operativas, no consulta automática de ajustes en cada llamada: no cambiar plan ni apagarZDR mientras se use.

- https://console.groq.com/docs/legal/services-agreement/
- https://console.groq.com/docs/your-data
- https://console.groq.com/settings/data-controls
- https://console.groq.com/settings/billing/plans
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/settings/limits
- https://console.groq.com/docs/models

CuentaGPTOSS120B:30RPM,1000RPD,8KTPM,200KTPD. Modelo distinto deDeepSeek, sin equivalencia de calidad ni SLA afirmada.8KTPM puede impedir prompts grandes aunque el modelo tenga más contexto. Rate limit provoca degradación, no gasto ni upgrade automático. Estimaciones internas de costes no son facturaFree.

## Código y pruebas

Solo ChatService usa fábrica de respaldo, jobs/tesis mantienen fábrica previa. Opt-in apagado por defecto, exige clave+Freeconfirmado+ZDRconfirmado. Endpoint/modelo fijosGroqGPTOSS120B. PrimarioOpenCode debe resolver a modelo verificado gratis antes de red. Routercompuesto honesto sin ampliarallowlistglobal. Solo backend recibe variablescompose, no workers.

Respaldo tras25s o fallo previo, primario conserva45s totales y puede ganar. Perdedor cancelado/recogido, sin asumir cancelación remota. Groq12s petición/15s total,cero reintentos,effortlow,max2400. Salida truncada/degradada/rechazada no gana. Prov/modelo reales en chat general.

225regresiones pasan+Ruff. Incluyen carreras/cancelación/deadline/truncación/failclosed/HTTPadaptador con transportesimulado; ambos canarios de consejo conocidos rechazados; prueba estructurada muestra transferencia íntegra de mensajes de ejemplo SINTÉTICOS y boundaryañadido. No QAcon cuenta/sesión/carteraNico. Pruebas reales previas de este adaptador con prompts públicos y datos enteramentesintéticos: general0.697/0.592s completos, estructurado1.518sJSON/citasválidas (fixturefinanciero explícitamentesintético). Primerfixturetipofuenteincorrectofalló y se corrigiófixture,sinrelajarguardas. Es evidencia básica, no calidad exhaustiva ni cartera grande. Sin nuevas llamadas aOpenCode.

## Rollout

No activado en producción ni mergeautorizado aún. NuevoSHA necesita auditoría+autorizaciónexacta+CIgreen. Activación exige rollback deimagen/configypruebaacotadasindatosNico. Rollback apagarGROQ_CHAT_FALLBACK_ENABLED y restaurarimagen/config. No se promete disponibilidadtotalrestaurada. #1091local es independiente.

## Corrección de la carrera tras auditoría

El head inicial cancelaba al primario al recibir HTTP200 de Groq, antes de las guardas del producto. Se rechazó ese comportamiento. Ahora cada candidato se valida dentro de su tarea y antes de que pueda ganar: idioma/integridad, JSON y secciones/citas del mismo contrato estructurado y campos de confianza; en general, idioma y guarda de salida general existente. El filtro educativo adicional sigue aplicándose a Groq. Si Groq se rechaza, el primario permanece vivo hasta responder o agotar su plazo. La respuesta ganadora vuelve a pasar por el flujo habitual; no se relaja su guarda.

La validación se liga a una copia por petición del wrapper, sin estado mutable global de contexto. El registro de presupuesto se ejecuta una vez por cada candidato devuelto, incluso si se rechaza, y no otra vez al publicar al ganador. Las excepciones de validación se convierten en candidato rechazado, no en éxito de transporte.

230regresiones nuevas pasan+Ruff. Canarios reproducen primario válido a0.08s frente a respaldo rápido inválido a0.01s: noJSON, citas inexistentes e idioma inglés. En todos gana el primario válido con citation_verification=true y no se cancela. Canario general de idioma inválido y aislamiento entre dos validadores por petición también pasan. No QAcon datos reales ni nuevas llamadas upstream para estos canarios.
