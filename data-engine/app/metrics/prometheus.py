"""Exposicion Prometheus de las metricas de backend (#E5).

Es un contrato estándar: cualquiera que ya tenga un Prometheus lo consume sin
instalar nada, y sin dependencias nuevas (el formato de texto son lineas
``nombre{etiquetas} valor`` con ``# HELP`` y ``# TYPE`` encima).

TRES REGLAS que se deciden aqui y no en Prometheus:

1. **Una serie por (ruta, metodo, codigo).** Las etiquetas son la plantilla de
   ruta (nunca la URL cruda), el metodo y el codigo. Un ticker real dentro de
   una etiqueta es un scrape con miles de series: por eso la plantilla lleva
   ``{ticker}`` y el valor real no sale de aqui.
2. **El tenant viaja como etiqueta.** Las metricas se particionan por tenant en
   la BD y un scrape necesita poder filtrar. Prometheus no puede filtrar por una
   dimension que no este en la linea, asi que va como etiqueta. Exponglo todo de
   golpe es correcto; quien un scrape compartido y datos de varios tenants
   deberia exponer `/metrics` por tenant, no reescribir el formato.
3. **N/D no se expone como 0.** Una serie ausente es "no medido"; un 0 es "lo
   medimos y dio cero". Por eso hay lineas para la propia AUSENCIA
   (``*_no_medible``, que vale 1), que es la unica forma honesta de que un
   alertable se dispare por falta de datos.

Los histogramas se emiten con ``_bucket{le="..."}`` acumulativo, que es lo que
``histogram_quantile`` espera. Los percentiles ya calculados se exponen aparte
como gauges, para poder alertar sobre el numero y no sobre la estimacion del
store.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.models.metrics import (
    LATENCY_BUCKET_COLUMNS,
    LATENCY_BUCKET_EDGES,
    ApiLatencyWindow,
    EvidenceCoverageSnapshot,
    QueueDepthSnapshot,
    ThesisHitRateCell,
)

PREFIX = "cavaai_"
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

EXCLUSION_SERIES = {
    "excluded_neutral": "decision_neutra",
    "excluded_rating_unknown": "rating_desconocido",
    "excluded_no_entry_price": "sin_precio_entrada",
    "excluded_no_exit_price": "sin_precio_salida",
    "excluded_too_early": "demasiado_temprano",
    "excluded_tie": "empate",
    "excluded_no_benchmark": "sin_benchmark",
}

QUEUE_FIELDS = {
    "encolado": ("pending", "Mensajes en la lista, esperando a que un worker los coja."),
    "retrasado": ("delayed", "Mensajes con retardo programado."),
    "en_curso": ("in_flight", "Mensajes que un worker cogio y aun no ha hecho ack."),
    "fallidos": ("dead_lettered", "Cartas muertas: se agotaron los reintentos."),
    "procesados": ("processed", "Mensajes completados con exito (contador del worker)."),
    "fallos": ("failed", "Mensajes que fallaron (contador del worker)."),
    "reintentos": ("retried", "Mensajes reencolados tras un fallo (contador del worker)."),
    "saltados": ("skipped", "Mensajes saltados por limite de reintentos."),
    "workers_vivos": ("workers_live", "Workers con latido dentro del timeout de Dramatiq."),
}


def _escape(value: str) -> str:
    """Escapa el valor de una etiqueta: barra invertida, comilla y salto de linea."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(pairs: dict[str, object]) -> str:
    if not pairs:
        return ""
    body = ",".join(f'{key}="{_escape(str(value))}"' for key, value in pairs.items())
    return "{" + body + "}"


def _block(name: str, kind: str, help_text: str, samples: Sequence[str]) -> list[str]:
    """Un trio HELP/TYPE/muestras. Una seccion sin muestras no se emite."""
    if not samples:
        return []
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", *samples]


def _tenant_label(tenant_id: int | None) -> dict[str, object]:
    return {"tenant": tenant_id if tenant_id is not None else "none"}


def latency_metrics(rows: Sequence[ApiLatencyWindow], tenant_id: int | None) -> list[str]:
    counts: list[str] = []
    errors: list[str] = []
    buckets: list[str] = []
    overhead_sum: list[str] = []
    overhead_max: list[str] = []
    for row in rows:
        labels = dict(
            _tenant_label(tenant_id),
            route=row.route_template,
            method=row.method,
            status=str(row.status_code),
            window=row.window_size,
        )
        counts.append(f"{PREFIX}latencia_peticiones_total{_labels(labels)} {row.request_count}")
        errors.append(f"{PREFIX}latencia_errores_total{_labels(labels)} {row.error_count}")
        cumulative = 0
        for name, edge in zip(LATENCY_BUCKET_COLUMNS, LATENCY_BUCKET_EDGES, strict=True):
            cumulative += int(getattr(row, name) or 0)
            buckets.append(
                f"{PREFIX}latencia_segundos_bucket{_labels(dict(labels, le=str(edge)))} "
                f"{cumulative / 1000.0}"
            )
        cumulative += int(row.overflow or 0)
        buckets.append(
            f'{PREFIX}latencia_segundos_bucket{_labels(dict(labels, le="+Inf"))} '
            f"{cumulative / 1000.0}"
        )
        if row.overhead_samples:
            overhead_sum.append(
                f"{PREFIX}latencia_sobrecarga_segundos_total{_labels(labels)} "
                f"{float(row.overhead_sum_ms or 0.0) / 1000.0}"
            )
            overhead_max.append(
                f"{PREFIX}latencia_sobrecarga_segundos_max{_labels(labels)} "
                f"{float(row.overhead_max_ms or 0.0) / 1000.0}"
            )
    return [
        *_block(
            PREFIX + "latencia_peticiones_total", "counter",
            "Peticiones HTTP agregadas por ventana, ruta, metodo y codigo.", counts,
        ),
        *_block(
            PREFIX + "latencia_errores_total", "counter",
            "Peticiones con codigo 5xx en la misma agrupacion.", errors,
        ),
        *_block(
            PREFIX + "latencia_segundos_bucket", "histogram",
            "Histograma de duracion; la media no describe ni el cache hit ni la ingesta.",
            buckets,
        ),
        *_block(
            PREFIX + "latencia_sobrecarga_segundos_total", "counter",
            "Coste acumulado del propio middleware de latencia, medido en el request.",
            overhead_sum,
        ),
        *_block(
            PREFIX + "latencia_sobrecarga_segundos_max", "gauge",
            "Peor sobrecarga del middleware observada en la ventana.", overhead_max,
        ),
    ]


def queue_metrics(rows: Sequence[QueueDepthSnapshot]) -> list[str]:
    samples: dict[str, list[str]] = {key: [] for key in QUEUE_FIELDS}
    ages: list[str] = []
    missing: list[str] = []
    for row in rows:
        labels = {"queue": row.queue_name, "window": row.window_size}
        for key, (attribute, _help_text) in QUEUE_FIELDS.items():
            value = getattr(row, attribute)
            if value is None:
                missing.append(
                    f"{PREFIX}cola_no_medida{_labels(dict(labels, campo=key))} 1"
                )
                continue
            samples[key].append(f"{PREFIX}cola_{key}{_labels(labels)} {value}")
        if row.oldest_age_s is not None:
            ages.append(
                f"{PREFIX}cola_edad_mas_viejo_segundos{_labels(labels)} {row.oldest_age_s}"
            )
        if row.status == "incidente":
            missing.append(
                f'{PREFIX}cola_incidente'
                f'{_labels(dict(labels, motivo=row.incident_reason or "sin_motivo"))} 1'
            )
    out: list[str] = []
    for key, (_attribute, help_text) in QUEUE_FIELDS.items():
        out += _block(PREFIX + f"cola_{key}", "gauge", help_text, samples[key])
    out += _block(
        PREFIX + "cola_edad_mas_viejo_segundos", "gauge",
        "Antiguedad del trabajo mas viejo encolado; la metrica que avisa de un worker parado.",
        ages,
    )
    out += _block(
        PREFIX + "cola_no_medida", "gauge",
        "Campos que NO se pudieron medir. Vale 1: es un dato que falta, no un cero.", missing,
    )
    return out


def hit_rate_metrics(
    rows: Sequence[ThesisHitRateCell], tenant_id: int | None
) -> list[str]:
    numerators: list[str] = []
    denominators: list[str] = []
    excluded: list[str] = []
    rates: list[str] = []
    alphas: list[str] = []
    missing: list[str] = []
    for row in rows:
        labels = dict(
            _tenant_label(tenant_id),
            horizon=str(row.horizon_days),
            decision=row.decision,
            sector=row.sector,
            evidencia=row.evidence_bucket,
        )
        numerators.append(f"{PREFIX}hit_rate_aciertos{_labels(labels)} {row.hits}")
        denominators.append(f"{PREFIX}hit_rate_evaluados{_labels(labels)} {row.evaluated}")
        for attribute, reason in EXCLUSION_SERIES.items():
            value = int(getattr(row, attribute) or 0)
            if value:
                excluded.append(
                    f"{PREFIX}hit_rate_excluidos{_labels(dict(labels, motivo=reason))} {value}"
                )
        if row.hit_rate is None:
            missing.append(f"{PREFIX}hit_rate_no_medible{_labels(labels)} 1")
        else:
            rates.append(f"{PREFIX}hit_rate{_labels(labels)} {row.hit_rate}")
        if row.alpha is None:
            missing.append(
                f"{PREFIX}hit_rate_alpha_no_medible"
                f'{_labels(dict(labels, motivo=row.benchmark_reason or "sin_benchmark"))} 1'
            )
        else:
            alphas.append(f"{PREFIX}hit_rate_alpha{_labels(labels)} {row.alpha}")
    return [
        *_block(
            PREFIX + "hit_rate_aciertos", "gauge",
            "Numerador del hit-rate de tesis.", numerators,
        ),
        *_block(
            PREFIX + "hit_rate_evaluados", "gauge",
            "Denominador (aciertos + fallos). Sin esto el ratio no significa nada.",
            denominators,
        ),
        *_block(
            PREFIX + "hit_rate_excluidos", "gauge",
            "Tesis excluidas por motivo. Un hit-rate sin excluidos es propaganda.", excluded,
        ),
        *_block(
            PREFIX + "hit_rate", "gauge",
            "Aciertos / evaluados. No se expone cuando el denominador es 0.", rates,
        ),
        *_block(
            PREFIX + "hit_rate_alpha", "gauge",
            "Retorno medio menos el del benchmark en las mismas fechas.", alphas,
        ),
        *_block(
            PREFIX + "hit_rate_no_medible", "gauge",
            "Celdas con denominador 0: el ratio NO se expone.", missing,
        ),
    ]


def _pct(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else 100.0 * numerator / denominator


def evidence_metrics(
    snapshot: EvidenceCoverageSnapshot | None, tenant_id: int | None
) -> list[str]:
    if snapshot is None:
        return []
    labels = _tenant_label(tenant_id)
    gauges: dict[str, tuple[str, float | None]] = {
        "evidencia_pct_materiales": (
            "claims materiales con evidencia", _pct(snapshot.material_with_evidence,
                                                    snapshot.material_claims),
        ),
        "evidencia_pct_oficial": (
            "claims materiales con fuente verificada (OFICIAL)",
            _pct(snapshot.material_with_official, snapshot.material_claims),
        ),
        "evidencia_pct_inferida": (
            "claims materiales con fuente inferida",
            _pct(snapshot.material_with_inferred, snapshot.material_claims),
        ),
        "evidencia_pct_todos": (
            "todos los claims con evidencia, materiales o no",
            _pct(snapshot.claims_with_evidence, snapshot.claims_total),
        ),
        "evidencia_cobertura_p10": ("p10 de cobertura por tesis", snapshot.coverage_p10),
        "evidencia_cobertura_p50": ("p50 de cobertura por tesis", snapshot.coverage_p50),
        "evidencia_cobertura_p90": ("p90 de cobertura por tesis", snapshot.coverage_p90),
        "evidencia_cobertura_media": ("media de cobertura por tesis", snapshot.coverage_mean),
        "evidencia_claims_sin_soporte": (
            "claims sin soporte segun SourceAuditor", float(snapshot.unsupported_total),
        ),
        "evidencia_claims_debiles": (
            "claims debiles segun SourceAuditor", float(snapshot.weak_total),
        ),
        "evidencia_conflictos_datos": (
            "conflictos de datos segun SourceAuditor", float(snapshot.data_conflicts_total),
        ),
        "evidencia_auditorias": ("auditorias del SourceAuditor", float(snapshot.audits_total)),
        "evidencia_auditorias_pasadas": (
            "auditorias que pasaron", float(snapshot.audits_passed),
        ),
    }
    out: list[str] = []
    missing: list[str] = []
    for name, (help_text, value) in gauges.items():
        if value is None:
            missing.append(f"{PREFIX}{name}_no_medible{_labels(labels)} 1")
            continue
        out += _block(PREFIX + name, "gauge", help_text, [f"{PREFIX}{name}{_labels(labels)} {value}"])
    out += _block(
        PREFIX + "evidencia_cobertura_tesis_bucket", "gauge",
        "Histograma de cobertura por tesis. Una sola barra con toda la masa es el hallazgo.",
        [
            f'{PREFIX}evidencia_cobertura_tesis_bucket{_labels(dict(labels, tramo=bucket))} {count}'
            for bucket, count in (snapshot.coverage_histogram or {}).items()
        ],
    )
    out += _block(
        PREFIX + "evidencia_no_medible", "gauge",
        "Porcentajes que NO se exponen por falta de denominador.", missing,
    )
    return out


def render(
    *,
    latency: Sequence[ApiLatencyWindow] = (),
    queues: Sequence[QueueDepthSnapshot] = (),
    hit_rates: Sequence[ThesisHitRateCell] = (),
    evidence: EvidenceCoverageSnapshot | None = None,
    tenant_id: int | None = None,
) -> str:
    """Documento Prometheus completo. Las secciones sin muestras no se emiten."""
    blocks = [
        *latency_metrics(latency, tenant_id),
        *queue_metrics(queues),
        *hit_rate_metrics(hit_rates, tenant_id),
        *evidence_metrics(evidence, tenant_id),
    ]
    return "\n".join(blocks) + "\n"