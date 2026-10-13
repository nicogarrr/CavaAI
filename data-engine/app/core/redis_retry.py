"""Reintentos de redis-py: se conserva el comportamiento de fallo rapido.

redis-py 6 cambio el defecto de los clientes standalone a 3 reintentos con backoff
exponencial con jitter. Todos los clientes de este servicio tienen timeouts cortos A
PROPOSITO (rate limit, replay, cache de respuestas, sondas de salud, leases, cuota LLM):
fallan rapido y el llamador degrada (fail-open o "no disponible"). Con reintentos, un
Redis caido convertiria esos 0,25-2 s en varios segundos dentro de la peticion o de la
sonda /health/ready. Cada ``from_url`` pasa ``retry=no_retry()`` (redis-py 5: era el
comportamiento por defecto) y el guard ``tests/test_redis_no_retry_guard.py`` lo exige.
"""

from __future__ import annotations

from typing import Any


def no_retry() -> Any:
    """``Retry`` de 0 reintentos para clientes sync (``redis.from_url``)."""
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    return Retry(NoBackoff(), 0)


def no_retry_async() -> Any:
    """``Retry`` de 0 reintentos para clientes ``redis.asyncio``."""
    from redis.asyncio.retry import Retry
    from redis.backoff import NoBackoff

    return Retry(NoBackoff(), 0)
