"""Small Redis-backed cache with in-process fallback."""

from __future__ import annotations

import json
import os
import time
from typing import Callable, TypeVar

T = TypeVar("T")

_memory_cache: dict[str, tuple[float, object]] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def cached_call(key: str, fn: Callable[[], T], ttl_seconds: int = 300) -> T:
    redis_client = _get_redis()
    if redis_client is not None:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
        value = fn()
        redis_client.setex(key, ttl_seconds, json.dumps(value))
        return value

    now = time.time()
    cached = _memory_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]  # type: ignore[return-value]
    value = fn()
    _memory_cache[key] = (now + ttl_seconds, value)
    return value

