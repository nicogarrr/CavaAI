from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.core.rate_limit as rate_limit_module
from app.core.config import Settings
from app.core.rate_limit import RateLimitMiddleware


def test_expensive_requests_are_limited_per_identity(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="staging",
        rate_limit_requests_per_minute=10,
        rate_limit_expensive_requests_per_minute=2,
    )
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: settings)
    counts: dict[str, int] = {}

    async def increment(_self, key, _bucket, _redis_url, *, use_redis):
        assert use_redis is True
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(RateLimitMiddleware, "_increment", increment)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/chat")
    def chat():
        return {"ok": True}

    client = TestClient(app)
    headers = {"X-CavaAI-Tenant": "tenant-a", "X-CavaAI-User": "user-a"}

    first = client.post("/api/chat", headers=headers)
    second = client.post("/api/chat", headers=headers)
    blocked = client.post("/api/chat", headers=headers)
    other_user = client.post(
        "/api/chat",
        headers={"X-CavaAI-Tenant": "tenant-a", "X-CavaAI-User": "user-b"},
    )

    assert first.status_code == second.status_code == other_user.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert second.headers["X-RateLimit-Remaining"] == "0"
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Rate limit exceeded"}
    assert int(blocked.headers["Retry-After"]) in range(1, 61)


def test_health_and_options_bypass_rate_limiting(monkeypatch):
    settings = Settings(_env_file=None, app_env="staging")
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: settings)

    async def should_not_increment(*_args, **_kwargs):
        raise AssertionError("bypassed requests must not consume a rate-limit slot")

    monkeypatch.setattr(RateLimitMiddleware, "_increment", should_not_increment)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.options("/api/chat")
    def options():
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.options("/api/chat").status_code == 200
