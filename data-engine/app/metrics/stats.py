"""Estadistica compartida por las cuatro metricas (#E5).

Todo aqui es determinista y sin estado: mismas entradas, mismos numeros. Nada
de aproximaciones "razonables" ni de promedios donde el percentil es lo que
contesta la pregunta. El unico interpolation permitido es el lineal dentro del
cajon del histograma, que es el metodo que usan las librerias de histogramas de
prometheus y esta documentado en cada sitio donde se usa.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from app.metrics import config


def percentile(sorted_values: Sequence[float], q: float) -> float | None:
    """Percentil (0..1) por interpolacion lineal sobre valores YA ordenados.

    `None` cuando no hay ninguna muestra: el percentil de una lista vacia no es
    0, es "no medido", y confundirlos es el bug que este modulo evita.
    """
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    q = min(1.0, max(0.0, q))
    position = q * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def quantiles(values: Iterable[float], qs: Sequence[float]) -> dict[str, float | None]:
    """p10/p50/p90 (o los que se pidan) de una muestra sin ordenar in-place."""
    ordered = sorted(float(value) for value in values)
    return {f"p{int(round(q * 100))}": percentile(ordered, q) for q in qs}


def bucket_counts(values: Iterable[float], edges: Sequence[float]) -> list[int]:
    """Conteo por cajon con borde superior `edges[i]` (semiabierto a la derecha).

    Un valor cae en el primer cajon cuyo borde superior es >= valor. El
    remanente (mayor que el ultimo borde) lo cuenta el llamante como
    "overflow", y asi el total de los cajones mas el overflow es el total de la
    muestra, siempre.
    """
    counts = [0] * len(edges)
    for value in values:
        for index, edge in enumerate(edges):
            if value <= edge:
                counts[index] += 1
                break
    return counts


def histogram_from_buckets(edges: Sequence[float], counts: Sequence[int]) -> dict[str, int]:
    """Histograma serializable `{"<=1": n, ...}` + `"overflow"`."""
    buckets = {f"le_{_fmt_edge(edge)}": int(count) for edge, count in zip(edges, counts, strict=True)}
    buckets["overflow"] = 0
    return buckets


def _fmt_edge(edge: float) -> str:
    return str(int(edge)) if float(edge).is_integer() else str(edge)


def percentile_from_histogram(
    edges: Sequence[float],
    counts: Sequence[int],
    overflow: int,
    q: float,
) -> float | None:
    """Percentil estimado desde un histograma de bordes superiores.

    Interpolacion lineal DENTRO del cajon que contiene el percentil, y el borde
    superior del ultimo cajon finito cuando la masa restante cae en `overflow`
    (la mediana de un histograma no puede ser mayor que su ultimo tope
    conocido, y declarar un numero mayor seria inventarlo).
    """
    total = sum(counts) + max(0, overflow)
    if total <= 0:
        return None
    q = min(1.0, max(0.0, q))
    target = q * total
    seen = 0
    previous_edge = 0.0
    for edge, count in zip(edges, counts, strict=True):
        count = int(count)
        if count <= 0:
            previous_edge = float(edge)
            continue
        upper_position = seen + count
        if target <= upper_position:
            if q >= 1.0:
                return float(edge)
            if count == 1:
                return float(edge)
            # Interpolacion dentro del cajon (y, y_upper) -> (a, b).
            offset = (target - seen) / count
            return previous_edge + (float(edge) - previous_edge) * offset
        seen = upper_position
        previous_edge = float(edge)
    if overflow > 0 and previous_edge > 0:
        # La cola se sale del histograma: se declara el tope conocido y el
        # llamante puede anadir que es un minimo, no una medida exacta.
        return float(previous_edge)
    return float(previous_edge) if previous_edge else None


def window_start(moment: datetime, window_size: str) -> datetime:
    """Trunca `moment` al inicio de su ventana, en UTC **naive**.

    Naive a proposito: las tablas de metricas son `timestamp without time zone`
    y se escriben siempre en UTC, porque la zona la fija este modulo y no la
    sesion de la BD (ver `app/models/metrics.py`). Devolver un aware aqui
    meteria un `+00:00` en el valor que se escribe y dejaria de casar con las
    consultas.
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    if window_size == config.WINDOW_MINUTE:
        return moment.replace(second=0, microsecond=0)
    if window_size == config.WINDOW_HOUR:
        return moment.replace(minute=0, second=0, microsecond=0)
    if window_size == config.WINDOW_DAY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(minute=0, second=0, microsecond=0)


def next_window_start(start: datetime, window_size: str) -> datetime:
    from datetime import timedelta

    if window_size == config.WINDOW_MINUTE:
        return start + timedelta(minutes=1)
    if window_size == config.WINDOW_HOUR:
        return start + timedelta(hours=1)
    return start + timedelta(days=1)


def indisponible(motivo: str) -> dict:
    """El N/D de la API: valor ausente MAS el motivo.

    Nunca `0`. Un 0 dice "lo medimos y dio cero"; un N/D dice "no lo
    medimos". Confundirlos convierte un hueco de datos en un hallazgo.
    """
    return {"estado": "N/D", "valor": None, "motivo": motivo}


def disponible(valor: object) -> dict:
    return {"estado": "ok", "valor": valor, "motivo": None}


def nd_or_value(bucket: dict, key: str = "valor") -> object:
    """Lee `valor` de un bloque metrics; devuelve None si el bloque es N/D."""
    if not isinstance(bucket, dict):
        return None
    if bucket.get("estado") != "ok":
        return None
    return bucket.get(key)