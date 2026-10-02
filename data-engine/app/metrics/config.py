"""Ajustes de las metricas de backend (#E5).

Viven aqui y no en `app/core/config.py` porque `Settings` es un fichero
compartido por 17 agentes en paralelo y anadir tres flags de observabilidad es
pedir un conflicto por el cambio mas tonto del repo. Se leen del entorno con el
mismo criterio de pydantic-settings (el entorno gana a los defaults) y todos
tienen default sensato, de modo que un despliegue que no configure nada
funciona igual: la instrumentacion esta activa fuera de `test` y apagada en
`test`, donde escribir metricas ensuciaria la base de la sesion.

Ninguno de estos knobs es un secreto ni una credencial.
"""

from __future__ import annotations

import os
from typing import Final

# Ventanas de latencia. El minuto es la granularidad de un incidente; la hora
# es la que se consulta. La tabla guarda las dos y la poda conserva mas horas
# que dias (ver RETENTION_DAYS).
WINDOW_MINUTE: Final = "minute"
WINDOW_HOUR: Final = "hour"
WINDOW_DAY: Final = "day"
WINDOW_SIZES: Final = (WINDOW_MINUTE, WINDOW_HOUR, WINDOW_DAY)

# Retencion DECLARADA por tabla, en dias. Una tabla de metricas sin poda es una
# bomba de relojería en Postgres: crece sin limite y nunca la lee nadie entera.
RETENTION_DAYS: Final[dict[str, int]] = {
    # Latencia: 7 dias de minutos (diagnostico de incidente), 60 de horas,
    # 400 de dias (comparativa trimestral, 4 anos de historia de SLO).
    "api_latency_windows:minute": 7,
    "api_latency_windows:hour": 60,
    "api_latency_windows:day": 400,
    # Cola: 14 dias de snapshots por cola son 6 colas x 24 x 14 = ~2k filas.
    "queue_depth_snapshots": 14,
    # Hit-rate y evidencia: un snapshot por tenant y dia, y solo se consulta
    # la serie. 800 dias = ~2 anos de track record.
    "thesis_hit_rate_cells": 800,
    "evidence_coverage_snapshots": 800,
}

# Cardinalidad maxima de plantillas de ruta distintas por ventana antes de
# colapsar el resto en "__overflow__". Con 190 rutas registradas y ~5 codigos
# de estado habituales el techo real anda por 300-400 series por ventana; 800
# deja margen para codigos raros sin permitir que un escaner de URLsgender el
# numero de filas. Un LRU de plantillas vivira aparte por proceso.
MAX_ROUTE_SERIES: Final = 800

# Series pendientes en el buffer en memoria antes de volcar a la BD. Volcar es
# un UPSERT por serie: hacerlo por request seria contention en la tabla de
# negocio, que es exactamente el antipatron que este modulo evita.
FLUSH_MAX_SERIES: Final = 200
FLUSH_INTERVAL_SECONDS: Final = 5.0

# --- Cola -------------------------------------------------------------------
# Umbral de "trabajo mas viejo encolado" por encima del cual, con cero trabajo
# en curso y cero workers vivos, se declara INCIDENTE (y no un statistic).
# 300 s es el tiempo que un worker tarda en reiniciar en un despliegue normal;
# por debajo es rutina, por encima el trabajo se queda parado.
QUEUE_STALL_SECONDS: Final = 300.0

# Dramatiq considera un worker muerto a los 60 s sin heartbeat
# (RedisBroker.heartbeat_timeout); el margen solo evita el borde.
QUEUE_DEAD_WORKER_SECONDS: Final = 90.0

# Techo de mensajes decodificados por cola al buscar la edad del mas viejo.
# Decodificar toda una cola grande en cada sonda es O(n) sobre JSON: con el
# techo, el resultado es una estimacion HONESTA y se declara como tal
# (`oldest_age_exhaustive: false`), nunca una edad inventada.
QUEUE_AGE_SAMPLE_LIMIT: Final = 500

# Colas queCIAL se vigilan. Sale de los `-Q` de docker-compose; se puede
# ampliar por entorno sin desplegar. El sondeo ademas descubre en Redis
# cualquier cola que no este en la lista.
KNOWN_QUEUES: Final = ("default", "prices", "thesis", "kpis", "alerts", "gdelt")

# --- Hit-rate ---------------------------------------------------------------
# Horizonte en dias naturales desde la fecha de publicacion de la tesis.
HIT_RATE_HORIZONS: Final = (30, 90, 180)

# `materiality_score` va de 0 a 10 y el repo ya fija 7 como corte de
# materialidad en claim_scope.py ("un claim con materiality_score >= 7 y sin
# evidencia cuesta 8 puntos"). Se reutiliza ese corte y no uno nuevo.
MATERIALITY_THRESHOLD: Final = 7

# Indice de referencia. Es el mismo ^GSPC que usa market_regime_quant.paired_beta;
# si no hay serie de precios para el, el alpha sale N/D con motivo, nunca 0.
BENCHMARK_TICKER: Final = "^GSPC"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "s"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int_list(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = _env(name, "")
    if not raw:
        return default
    try:
        values = tuple(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError:
        return default
    return values or default


def _app_env() -> str:
    try:
        from app.core.config import get_settings

        return str(get_settings().app_env).strip().lower()
    except Exception:  # noqa: BLE001 — la config nunca debe tumbar la metrica
        return os.environ.get("APP_ENV", "local").strip().lower()


def latency_enabled() -> bool:
    """El middleware mide; en `test` no, para no ensuciar la BD de la sesion."""
    return _env_bool("BACKEND_METRICS_LATENCY_ENABLED", _app_env() != "test")


def latency_window() -> str:
    window = _env("BACKEND_METRICS_LATENCY_WINDOW", WINDOW_HOUR)
    return window if window in WINDOW_SIZES else WINDOW_HOUR


def flush_interval_seconds() -> float:
    return max(0.5, _env_float("BACKEND_METRICS_FLUSH_INTERVAL_S", FLUSH_INTERVAL_SECONDS))


def flush_max_series() -> int:
    return max(1, _env_int("BACKEND_METRICS_FLUSH_MAX_SERIES", FLUSH_MAX_SERIES))


def max_route_series() -> int:
    return max(16, _env_int("BACKEND_METRICS_MAX_ROUTE_SERIES", MAX_ROUTE_SERIES))


def queue_stall_seconds() -> float:
    return max(1.0, _env_float("BACKEND_METRICS_QUEUE_STALL_S", QUEUE_STALL_SECONDS))


def queue_dead_worker_seconds() -> float:
    return max(1.0, _env_float("BACKEND_METRICS_QUEUE_DEAD_WORKER_S", QUEUE_DEAD_WORKER_SECONDS))


def queue_age_sample_limit() -> int:
    return max(10, _env_int("BACKEND_METRICS_QUEUE_AGE_SAMPLE", QUEUE_AGE_SAMPLE_LIMIT))


def known_queues() -> tuple[str, ...]:
    raw = _env("BACKEND_METRICS_QUEUES", "")
    if not raw:
        return KNOWN_QUEUES
    return tuple(item.strip() for item in raw.split(",") if item.strip()) or KNOWN_QUEUES


def hit_rate_horizons() -> tuple[int, ...]:
    return tuple(h for h in _env_int_list("BACKEND_METRICS_HORIZONS", HIT_RATE_HORIZONS) if h > 0)


def materiality_threshold() -> int:
    return max(0, _env_int("BACKEND_METRICS_MATERIALITY_MIN", MATERIALITY_THRESHOLD))


def benchmark_ticker() -> str:
    return _env("BACKEND_METRICS_BENCHMARK", BENCHMARK_TICKER)


def retention_days(table: str, window_size: str | None = None) -> int:
    key = f"{table}:{window_size}" if window_size else table
    return RETENTION_DAYS.get(key, RETENTION_DAYS.get(table, 90))