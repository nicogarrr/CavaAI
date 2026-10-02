"""Metricas de backend que hoy nadie puede responder (#E5).

Cuatro preguntas que sin esto son opiniones:

1. **Latencia por endpoint** (`app.metrics.latency`): middleware ASGI que
   etiqueta por PLANTILLA de ruta (no por URL), p50/p95/p99 desde un histograma,
   agregado por ventana en su propia tabla. Nunca un log por request.
2. **Profundidad de cola** (`app.metrics.queue`): encolado / en curso / fallido /
   reintentos y la EDAD del trabajo mas viejo, leida del layout de claves del
   `RedisBroker`. Trabajo parado con 0 en curso es un INCIDENTE, no un statistic.
3. **Hit-rate de tesis** (`app.metrics.thesis`): acertaron, con definicion
   determinista, regla de look-ahead, alpha contra ^GSPC y -- lo que la separa de
   la propaganda -- numerador, denominador y excluidos visibles en la misma fila.
4. **% de claims con evidencia** (`app.metrics.evidence`): material vs total,
   oficial vs inferido, breakdown del `SourceAuditor` en contadores, y la
   DISTRIBUCION (p10/p50/p90 + histograma) porque la media sola puede mentir.

Reglas transversales que atraviesan las cuatro:

- **Particionado por tenant** en la BD (las tablas son `TenantOwnedMixin`, asi que
  el `with_loader_criteria` de `app/core/database.py` las aísla igual que al
  resto). La excepcion es la cola: las colas de Dramatiq son infraestructura
  compartida y no tienen tenant, asi que esa tabla no lleva `tenant_id` y la API
  lo declara en vez de fingir un particionado.
- **N/D con motivo, nunca 0.** Un 0 dice "lo medimos y dio cero"; un N/D dice "no
  lo medimos". `app/metrics/stats.indisponible()` es el unico sitio donde se
  construye esa distinction.
- **Nada de PII en las etiquetas**: ni query string, ni tokens, ni tickers
  reales, ni el texto de un claim.
- **Los calculos pesados van precalculados** (`app.metrics.precompute`), nunca en
  el camino de un request.
"""

from __future__ import annotations

__all__ = [
    "config",
    "evidence",
    "latency",
    "precompute",
    "prometheus",
    "queue",
    "retention",
    "route_template",
    "stats",
    "thesis",
]