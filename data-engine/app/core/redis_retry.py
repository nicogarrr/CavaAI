"""Reintentos de redis-py: el fallo rapido queda fijado por contrato.

El defecto de 3 reintentos con backoff exponencial (redis-py 6) aplica al constructor
``Redis(host=...)``; con ``from_url`` el retry por defecto es ``None`` en redis-py 5 y 6
(verificado por la auditoria, sync y asyncio). Por tanto pasar ``retry=`` aqui NO cambia
el comportamiento actual: fija por contrato el fallo rapido y evita una regresion si el
defecto cambia en una version futura. Todos los clientes de este servicio tienen timeouts
cortos A PROPOSITO (rate limit, replay, cache de respuestas, sondas de salud, leases,
cuota LLM): fallan rapido y el llamador degrada. Cada ``from_url`` pasa
``retry=no_retry()`` y el guard ``tests/test_redis_no_retry_guard.py`` lo exige.
Limitacion conocida: el guard no vigila el constructor ``Redis(host=...)``, que es donde
si cambia el defecto; hoy no hay ninguno en ``app/``.
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
