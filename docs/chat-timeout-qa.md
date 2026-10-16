# Incidente: chat de cartera cortado antes del backend

2026-10-16. Base b7e2a333704b10cf014504d6895099a087376a92.

## Evidencia

La captura del propietario muestra "Que es el per?" seguido de "Error de
conexión.". A las 09:36:20 UTC el backend registró POST /api/chat, status 200,
50.2 s. Readiness seguía OK. El bridge registró timeouts y 502; ensayos de QA
contra el bridge compartido pudieron contribuir a la carga. Todos esos ensayos
se detuvieron. No se afirma una correlación de request ID con la captura.

Causa reproducible en código: chatWithPortfolio usaba researchRequest con el
presupuesto global de 15 s, mientras el LLM admite 45 s más trabajo de servicio.
PortfolioChat convertía cualquier excepción en "Error de conexión.". La página
no exportaba maxDuration y vercel.json tenía un patrón de páginas de 10 s. El
presupuesto de 15 s ya existe antes del cambio #1084. Un rollback de #1084 no
corrige ese presupuesto.

## Cambio acotado

- Solo POST /api/chat obtiene 55 s. Otros POST continúan en 15 s, GET rápidos
  en 8 s y el override explícito sigue teniendo prioridad.
- La página portfolio exporta maxDuration=60, aplicable a sus Server Actions.
  Research ya exportaba 60; no se cambian settings, plan, billing ni dominios.
- La acción devuelve errores de transporte conocidos como resultado recuperable,
  distinguiendo espera agotada e indisponibilidad. Autenticación y propiedad se
  validan antes; no se capturan como fallos de proveedor.
- La UI ya no diagnostica toda excepción como un error de conexión.

## Verificación

10/10 tests de contrato, con la acción y cliente reales y una identidad sintética.
Un servidor HTTP loopback retarda 16 s: supera el corte anterior de 15 s y la
acción devuelve el concepto de PER. Se comprueban propietario incorrecto,
clasificación del timeout, indisponibilidad sin filtrar diagnósticos y ventanas
55/60. ESLint de archivos modificados: exit 0. Sin LLM, sesión ni datos de Nico.

No es una prueba de sesión autenticada real de producción: el propietario
reintentará tras el despliegue. No se cambia el timeout LLM ni se promete que el
proveedor responda siempre. El presupuesto total solo evita cortar una respuesta
válida antes de su ventana. Un backend que supera 55 s produce un aviso de
reintento, no una respuesta inventada.

## Fuentes actuales de límites gratuitos

- https://vercel.com/docs/functions/configuring-functions/duration
  Hobby con Fluid: máximo 300 s. Se elige 60 s, no se requiere plan Pro.
- https://nextjs.org/docs/app/api-reference/file-conventions/route-segment-config/maxDuration
  Server Actions toman maxDuration de la página.
- https://vercel.com/docs/fluid-compute
  La configuración de código tiene prioridad sobre vercel.json.

Pendiente: CI, auditoría, permiso de SHA, despliegue y comprobación de la
configuración emitida por el build. No hay merge ni cambio de producción aquí.
