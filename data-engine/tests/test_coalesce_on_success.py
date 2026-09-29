"""Guardia de coalescencia de la cola de ingesta (_coalesce_on_success).

El backlog de default acumulaba re-encolados periodicos que se pisaban entre
si (p.ej. 125 refresh_rss_feeds = 31 h de cadencia de 15 min): ejecutar uno
deja obsoletos los demas. El decorador devuelve skipped cuando el job ya
devolvio "ok" dentro de su ventana. Invariantes:

1. Con marca fresca, la funcion NO se ejecuta y devuelve skipped.
2. Sin marca, ejecuta y marca SOLO si el resultado es "ok".
3. Un resultado error/partial nunca marca: los reintentos no se suprimen.
4. Redis caido es fail-open: ejecuta siempre y no propaga la excepcion.
"""

from __future__ import annotations

from app.workers import dramatiq_app
from app.workers.dramatiq_app import _coalesce_on_success


class FakeRedis:
    def __init__(self, stored=None, raises=False):
        self.stored = stored
        self.raises = raises
        self.set_calls = []

    def get(self, key):
        if self.raises:
            raise ConnectionError("redis caido")
        return self.stored

    def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))
        return True


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(dramatiq_app, "_redis_client", lambda: client)


def test_fresh_mark_skips_execution(monkeypatch):
    _patch_client(monkeypatch, FakeRedis(stored=b"1"))
    calls = []

    @_coalesce_on_success("job", 60)
    def job():
        calls.append(1)
        return {"status": "ok"}

    result = job()
    assert result["status"] == "skipped"
    assert result["reason"] == "fresh_within_window"
    assert calls == []


def test_ok_result_sets_mark_with_window(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)

    @_coalesce_on_success("job", 120, ("tenant_id",))
    def job(tenant_id=None):
        return {"status": "ok"}

    assert job(tenant_id=7) == {"status": "ok"}
    assert client.set_calls == [("coalesce:job:7", "1", 120)]


def test_error_result_never_marks(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)

    @_coalesce_on_success("job", 60)
    def job():
        return {"status": "error", "errors": [{"message": "boom"}]}

    assert job()["status"] == "error"
    assert client.set_calls == []


def test_redis_down_is_fail_open(monkeypatch):
    _patch_client(monkeypatch, FakeRedis(raises=True))
    calls = []

    @_coalesce_on_success("job", 60)
    def job():
        calls.append(1)
        return {"status": "ok"}

    assert job()["status"] == "ok"
    assert calls == [1]


def test_window_callable_receives_actor_kwargs(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)

    @_coalesce_on_success(
        "news",
        lambda scope="all", **_: 25 if scope == "tracked" else 500,
        ("scope",),
    )
    def news(tenant_id=None, scope="all"):
        return {"status": "ok"}

    news(scope="tracked")
    news(scope="all")
    assert client.set_calls == [
        ("coalesce:news:tracked", "1", 25),
        ("coalesce:news:all", "1", 500),
    ]
