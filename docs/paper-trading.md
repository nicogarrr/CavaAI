# Cartera simulada LLM

El módulo vive en ProPicks > Paper trading. No hay broker, dinero real ni llamadas LLM nuevas.

## Contrato para el generador

`POST /api/paper-trading/proposals` acepta una propuesta del generador existente:

```json
{
  "proposal_key": "run-id:ASTS:long",
  "ticker": "ASTS",
  "direction": "long",
  "horizon": "short",
  "thesis": "Texto de la tesis con riesgos y fuentes",
  "conviction": "0.8",
  "proposed_entry": "100",
  "stop": "90",
  "target": "120",
  "quantity": "1",
  "inference_basis": "Fuentes y razonamiento de la inferencia"
}
```

Este ejemplo es ilustrativo, no una propuesta real. `short` es un trade de 30 días desde la entrada, `five_years` una tesis de cinco años. Dirección `long` o `short`. Cantidad obligatoria, unidades simuladas, no una asignación de capital real. Convicción, entrada deseada, stop y objetivo son inferencias. El precio ejecutado nunca se acepta del cliente. Autor fijado a LLM. Clave idempotente por tenant, conflicto si cambia el contenido. Las propuestas no se editan ni se borran.

`GET /proposals`, `GET /scoreboard`, `POST /refresh`, `POST /proposals/{id}/close`, bajo el mismo prefijo y autenticación Research OS.

## Ejecución

Worker Dramatiq cada 30 minutos, máximo 50 símbolos por tenant por pasada, reutiliza la cotización Yahoo del motor. Solo `regularMarketPrice` con `regularMarketTime` y divisa sirven para ejecutar; las velas diarias no son fills. La cotización debe ser posterior a la propuesta, no futura y con antigüedad máxima de 24 horas. Últimos precios obsoletos se ocultan. Orden límite: largo entra al observar precio <= entrada deseada, corto >=. Gap fuera del intervalo stop/objetivo no abre. Stop/objetivo cierran al precio observado, nunca al nivel ideal. No se comprueban cruces intrabar entre sondeos. Cierres inmutables, quotes repetidas/fuera de orden se ignoran. Rotación por updated_at evita que los primeros 50 símbolos monopolicen la pasada.

## Medición y límites

Hit rate = porcentaje de posiciones cerradas con P&L bruto positivo. Se muestran ganadoras, perdedoras y neutras. P&L por horizonte y divisa, nunca suma USD con EUR. También bins de convicción para inspección/calibración posterior, sin ajustar automáticamente el modelo. Una tesis cerrada por stop antes de cinco años no constituye una predicción validada a cinco años.

No contempla comisiones, spread, financiación de cortos, dividendos, splits, conversiones FX, cash ledger, capital inicial ni rentabilidad ponderada de una cartera. Es un registro de ejecuciones spot brutas, no un track record neto fiable para inversión real. Una acción corporativa puede distorsionar el resultado y requiere revisión antes de usarlo para calibrar. No hay feed público externo: UI privada de CavaAI. No crea propuestas automáticamente: el generador LLM existente debe llamar al contrato cuando produzca su propuesta final. Sin datos o sin propuestas no se fabrican muestras.

Migración 0051 tras 0050. El integrador debe reservar/reordenar el número si otra rama añadió una migración en paralelo. No merge ni deploy por este cambio.
