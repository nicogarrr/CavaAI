from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings


EXPENSIVE_PATH_MARKERS = (
    "/chat",
    "/extract-kpis",
    "/long-term-model/generate",
    "/thesis/generate",
    "/snapshot/refresh",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Tenant/user/IP rate limit with Redis and a local-development fallback."""

    _local_counts: dict[tuple[str, int], int] = defaultdict(int)
    _lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if (
            not settings.rate_limit_enabled
            or request.url.path in {"/", "/health", "/health/live", "/health/ready"}
            or request.method == "OPTIONS"
        ):
            return await call_next(request)
        expensive = any(marker in request.url.path for marker in EXPENSIVE_PATH_MARKERS)
        limit = (
            settings.rate_limit_expensive_requests_per_minute
            if expensive
            else settings.rate_limit_requests_per_minute
        )
        if settings.app_env.lower() in {"local", "test"}:
            limit = max(limit, 10000)
        bucket = int(time.time() // 60)
        identity = ":".join(
            [
                request.headers.get("x-cavaai-tenant", "anonymous"),
                request.headers.get("x-cavaai-user", "anonymous"),
                request.client.host if request.client else "unknown",
                "expensive" if expensive else "standard",
            ]
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        key = f"cavaai:rate:{bucket}:{digest}"
        count = await self._increment(
            key,
            bucket,
            settings.redis_url,
            use_redis=settings.app_env.lower() not in {"local", "test"},
        )
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(60 - int(time.time() % 60))},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response

    async def _increment(
        self, key: str, bucket: int, redis_url: str, *, use_redis: bool
    ) -> int:
        try:
            if not use_redis:
                raise ConnectionError("local rate-limit store selected")
            import redis.asyncio as redis

            client = redis.from_url(redis_url, socket_connect_timeout=0.25)
            try:
                async with client.pipeline(transaction=True) as pipe:
                    pipe.incr(key)
                    pipe.expire(key, 75)
                    count, _ = await pipe.execute()
                return int(count)
            finally:
                await client.aclose()
        except Exception:
            # The fallback is process-local and intentionally only a resilience
            # path; production readiness already requires Redis health.
            async with self._lock:
                local_key = (key, bucket)
                self._local_counts[local_key] += 1
                for old_key in list(self._local_counts):
                    if old_key[1] < bucket - 1:
                        self._local_counts.pop(old_key, None)
                return self._local_counts[local_key]
