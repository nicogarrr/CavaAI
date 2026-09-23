"""Single-use nonce store for the signed identity bridge (anti-replay).

Every bound signature carries a random nonce that must be consumed exactly
once. Storage is Redis ``SET NX EX`` (atomic check-and-mark with TTL); when
Redis is unreachable the store degrades to a process-local TTL cache so a
Redis outage cannot turn into an auth outage (the local cache still blocks
replays within the process).
"""

from __future__ import annotations

import asyncio
import time

_local_nonces: dict[str, float] = {}
_local_lock = asyncio.Lock()


async def consume_nonce(
    nonce_key: str,
    *,
    ttl_seconds: int,
    redis_url: str,
    use_redis: bool = True,
) -> bool:
    """Return True when ``nonce_key`` is fresh (first and only use).

    Returns False when the nonce was already consumed inside the TTL window.
    """
    if use_redis:
        try:
            import redis.asyncio as redis

            client = redis.from_url(redis_url, socket_connect_timeout=0.25)
            try:
                acquired = await client.set(
                    nonce_key, "1", nx=True, ex=max(int(ttl_seconds), 1)
                )
            finally:
                await client.aclose()
            return bool(acquired)
        except Exception:  # noqa: BLE001 — fall back to the local TTL cache
            pass

    now = time.time()
    async with _local_lock:
        for key, expires in list(_local_nonces.items()):
            if expires <= now:
                _local_nonces.pop(key, None)
        if nonce_key in _local_nonces:
            return False
        _local_nonces[nonce_key] = now + max(int(ttl_seconds), 1)
        return True


def reset_local_nonces() -> None:
    """Test helper: clear the in-process nonce cache."""
    _local_nonces.clear()
