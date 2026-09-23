"""Rate limiting post-signature (dependency): ventana deslizante por
identidad, paths exentos, y 503 honesto cuando el store de produccion no
responde.

El middleware se sustituyo por la dependencia ``enforce_rate_limit`` (la
auditoria detecto que el middleware corria antes de auth y no podia
identificar al principal). En local/test el limite tiene suelo de 10000, asi
que los tests usan staging con un Redis inalcanzable: ``degrade_to_local``
mantiene el limite real configurado.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.core.rate_limit as rate_limit_module
from app.core.auth import ResearchPrincipal, get_research_principal
from app.core.config import Settings
from app.core.rate_limit import enforce_rate_limit

SECRET = "0123456789abcdef0123456789abcdef"
DEAD_REDIS = "redis://127.0.0.1:6399/15"


def _settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        app_env="staging",
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=10,
        rate_limit_expensive_requests_per_minute=2,
        redis_url=DEAD_REDIS,
    )
    base.update(overrides)
    return Settings(**base)


def _app(principal) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_research_principal] = lambda: principal

    @app.post("/api/chat", dependencies=[Depends(enforce_rate_limit)])
    def chat():
        return {"ok": True}

    @app.get("/api/vendors", dependencies=[Depends(enforce_rate_limit)])
    def vendors():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _clear_local_hits():
    rate_limit_module._local_hits.clear()
    yield
    rate_limit_module._local_hits.clear()


def _principal(user: str) -> ResearchPrincipal:
    return ResearchPrincipal(user_id=user, tenant_external_id="tenant-a")


def _client(monkeypatch, principal=None, **overrides) -> TestClient:
    monkeypatch.setattr(
        rate_limit_module, "get_settings", lambda: _settings(**overrides)
    )
    return TestClient(_app(principal))


def test_expensive_requests_limited_per_identity(monkeypatch):
    client = _client(monkeypatch, _principal("user-a"))
    first = client.post("/api/chat")
    second = client.post("/api/chat")
    blocked = client.post("/api/chat")
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert second.status_code == 200
    assert second.headers["X-RateLimit-Remaining"] == "0"
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Rate limit exceeded"}
    assert "Retry-After" in blocked.headers

    # Otra identidad: ventana independiente.
    other = _client(monkeypatch, _principal("user-b"))
    assert other.post("/api/chat").status_code == 200


def test_standard_requests_use_standard_limit(monkeypatch):
    client = _client(monkeypatch, _principal("user-a"))
    for _ in range(10):
        assert client.get("/api/vendors").status_code == 200
    assert client.get("/api/vendors").status_code == 429


def test_exempt_paths_bypass(monkeypatch):
    client = _client(monkeypatch, None)
    for _ in range(20):
        assert client.get("/health").status_code == 200


def test_disabled_setting_bypasses(monkeypatch):
    client = _client(monkeypatch, None, rate_limit_enabled=False)
    for _ in range(5):
        assert client.post("/api/chat").status_code == 200


def test_production_store_unavailable_returns_honest_503(monkeypatch):
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: _settings(
            app_env="production",
            research_auth_secret=SECRET,
            minio_secret_key="production-minio-secret-not-a-default",
            minio_access_key="production-minio-access-not-a-default",
        ),
    )
    client = TestClient(_app(_principal("user-a")))
    response = client.post("/api/chat")
    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limit backend unavailable"}
