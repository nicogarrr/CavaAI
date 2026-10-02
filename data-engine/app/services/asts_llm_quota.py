"""Atomic per-tenant rate and daily request budget for the ASTS catalog LLM.

A reservation counts attempted calls, including upstream failures. In production,
Redis failure blocks the LLM path. No expense or money is recorded for a free
provider model. Exact counts are shown in the endpoint response.

This module also hosts the generic implementation shared with the second-order
budget: both paths differ only in the ``QuotaNamespace`` they pass, so
``second_order_quota`` delegates here. Independent namespace per feature so one
cannot starve the other.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

_LOCAL: dict[str, tuple[int, int]] = {}
_LOCK = threading.Lock()

# Atomic across web workers: rejected calls do not consume either allowance.
_SCRIPT = """
local minute = tonumber(redis.call('GET', KEYS[1]) or '0')
local daily = tonumber(redis.call('GET', KEYS[2]) or '0')
if minute >= tonumber(ARGV[1]) or daily >= tonumber(ARGV[2]) then
  return {0, minute, daily}
end
minute = redis.call('INCR', KEYS[1])
daily = redis.call('INCR', KEYS[2])
if minute == 1 then redis.call('EXPIRE', KEYS[1], 120) end
if daily == 1 then redis.call('EXPIRE', KEYS[2], 172800) end
return {1, minute, daily}
"""


@dataclass(frozen=True)
class QuotaNamespace:
    """What makes one LLM budget a different budget: Redis keys, caps and error."""

    key: str
    minute_setting: str
    day_setting: str
    missing_tenant_error: str


_ASTS_NAMESPACE = QuotaNamespace(
    key="asts-llm",
    minute_setting="asts_llm_calls_per_minute",
    day_setting="asts_llm_calls_per_day",
    missing_tenant_error="ASTS catalog LLM needs a verified tenant",
)


def reserve_quota(tenant_id: int | str | None, settings, *, namespace: QuotaNamespace) -> dict:
    """Reserve one LLM call from ``namespace``'s budget, counting failures too."""
    if tenant_id is None:
        raise RuntimeError(namespace.missing_tenant_error)
    now = datetime.now(UTC)
    minute_key = f"cavaai:{namespace.key}:{tenant_id}:minute:{now:%Y%m%d%H%M}"
    day_key = f"cavaai:{namespace.key}:{tenant_id}:day:{now:%Y%m%d}"
    minute_cap = getattr(settings, namespace.minute_setting)
    day_cap = getattr(settings, namespace.day_setting)
    if settings.is_production:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.25, socket_timeout=0.5)
        try:
            # redis-py tipa eval como Awaitable[str] en stubs; el cliente sync devuelve la lista del script
            allowed, minute, daily = cast("list[int]", client.eval(_SCRIPT, 2, minute_key, day_key, minute_cap, day_cap))
        finally:
            client.close()
    else:
        with _LOCK:
            minute = _LOCAL.get(minute_key, (0, 0))[0]
            daily = _LOCAL.get(day_key, (0, 0))[0]
            allowed = int(minute < minute_cap and daily < day_cap)
            if allowed:
                minute += 1
                daily += 1
                _LOCAL[minute_key] = (minute, 0)
                _LOCAL[day_key] = (daily, 0)
    return {
        "allowed": bool(allowed), "minute_used": int(minute),
        "minute_limit": minute_cap, "day_used": int(daily), "day_limit": day_cap,
        "reset": "UTC calendar minute/day",
    }


def reserve_llm_call(tenant_id: int | str | None, settings) -> dict:
    """Reserve one ASTS catalog LLM call for ``tenant_id``."""
    return reserve_quota(tenant_id, settings, namespace=_ASTS_NAMESPACE)
