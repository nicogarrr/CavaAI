# Impuestos: integración del motor fiscal

La pestaña `/taxes` usa el motor existente de CavaAI inspirado en DeclaRenta.
No incorpora una dependencia nueva ni cambia reglas fiscales verificadas.

- Modelo 100: el mapeo sigue limitado al ejercicio 2025; para otros años se
  muestra el motivo del bloqueo, sin copiar casillas de otro ejercicio.
- TME del borrador: campo manual, inicialmente vacío, entre 0 y 100 % con
  dos decimales. `POST /api/taxes/report/{year}/preview` devuelve el mismo
  informe con la deducción por doble imposición recalculada. No guarda el
  porcentaje ni el informe. La lectura normal continúa sin TME; cambiar de
  año o regenerar descarta la vista previa.
- Una revisión manual pendiente sigue bloqueando el total de la deducción.
  La base sigue expresada en EUR y el país sigue siendo la aproximación por
  domicilio del emisor que ya documentaba el motor.
- Se muestra 0597 y el detalle de transmisiones, adquisiciones y resultado
  computable por venta, con diez ventas por página. Las posiciones fiscales
  también se muestran en páginas de diez; el CSV mantiene el informe visible
  y todas las posiciones, no solo la página seleccionada.
- Importes USD en posiciones: formato US (`$2,159.73`); EUR conserva el
  formato español. Ninguna cifra ausente se sustituye por cero.
- Modelo 720 conserva su chequeo de umbrales y descarga del borrador con
  notas y revisión manual. Esta entrega no añade presentación ante AEAT ni
  certifica que los cálculos sean una declaración lista para presentar.

## Comprobaciones

- TypeScript y ESLint de los componentes modificados.
- Guards fiscales del frontend.
- Tests herméticos de IRPF, informe FIFO, Modelo 720 y regla de dos meses.
- Render de componentes con datos sintéticos en móvil y escritorio,
  navegación de páginas y validación de TME negativo.

Pendiente para el pilot/auditor: publicar la rama y PR, verificar el flujo
con el backend desplegado y revisar con datos fiscales reales. No se ha
modificado producción ni importado información del usuario para las pruebas.
