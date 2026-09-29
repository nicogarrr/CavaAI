"""Guardia de coalescencia de la cola de ingesta (_coalesce_on_success).

El backlog de default acumulaba re-encolados periodicos que se pisaban entre
si (p.ej. 125 refresh_rss_feeds = 31 h de cadencia de 15 min). El decorador
usa un claim atomico (SET NX) al INICIO mas una marca fresca al terminar con
exito. Invariantes:

1. Dos ejecuciones concurrentes de la misma clave: solo UNA trabaja.
2. Sin claim ni marca, ejecuta y marca al terminar con status "ok".
3. Un resultado error/partial o una excepcion LIBERA el claim: el reintento
   o el siguiente tick del scheduler vuelven a correr el trabajo.
4. Redis caido es fail-open: ejecuta siempre y no propaga la excepcion.
"""

from __future__ import annotations

import threading

from app.workers import dramatiq_app
from app.workers.dramatiq_app import _coalesce_on_success


class FakeRedis:
    """Mini-Redis thread-safe con semantica SET NX real."""

    def __init__(self, raises=False):
        self.store = {}
        self.raises = raises
        self.set_calls = []
        self.lock = threading.Lock()

    def set(self, key, value, nx=False, ex=None):
        if self.raises:
            raise ConnectionError("redis caido")
        with self.lock:
            if nx and key in self.store:
                return None
            self.store[key] = value
            self.set_calls.append((key, value, nx, ex))
            return True

    def get(self, key):
        if self.raises:
            raise ConnectionError("redis caido")
        with self.lock:
            value = self.store.get(key)
        return value.encode() if isinstance(value, str) else value

    def delete(self, key):
        with self.lock:
            self.store.pop(key, None)


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(dramatiq_app, "_redis_client", lambda: client)


def test_concurrent_executions_single_winner(monkeypatch):
    """Dos hilos reclaman la misma clave a la vez: exactamente uno ejecuta."""
    client = FakeRedis()
    _patch_client(monkeypatch, client)
    started = threading.Event()
    release = threading.Event()
    executed = []
    results = []

    @_coalesce_on_success("job", 60)
    def job():
        started.set()  # el ganador avisa de que esta dentro con el claim
        assert release.wait(timeout=10)
        executed.append(1)
        return {"status": "ok"}

    winner = threading.Thread(target=lambda: results.append(job()["status"]))
    loser = threading.Thread(target=lambda: results.append(job()["status"]))
    winner.start()
    assert started.wait(timeout=10)  # el ganador ya tiene el claim
    loser.start()
    loser.join(timeout=10)  # debe saltarse mientras el ganador sigue dentro
    release.set()
    winner.join(timeout=10)
    assert len(executed) == 1
    assert sorted(results) == ["ok", "skipped"]


def test_ok_result_marks_fresh_and_next_run_skips(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)
    calls = []

    @_coalesce_on_success("job", 120, ("tenant_id",))
    def job(tenant_id=None):
        calls.append(1)
        return {"status": "ok"}

    assert job(tenant_id=7)["status"] == "ok"
    assert job(tenant_id=7)["status"] == "skipped"
    assert len(calls) == 1
    marks = [c for c in client.set_calls if c[1] == "done"]
    assert marks == [("coalesce:job:7", "done", False, 120)]


def test_error_result_releases_claim_for_retry(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)
    calls = []

    @_coalesce_on_success("job", 60)
    def job():
        calls.append(1)
        return {"status": "error", "errors": [{"message": "boom"}]}

    assert job()["status"] == "error"
    assert job()["status"] == "error"  # el reintento NO se suprime
    assert len(calls) == 2
    assert "coalesce:job" not in client.store


def test_exception_releases_claim_and_reraises(monkeypatch):
    client = FakeRedis()
    _patch_client(monkeypatch, client)
    calls = []

    @_coalesce_on_success("job", 60)
    def job():
        calls.append(1)
        raise RuntimeError("boom")

    try:
        job()
        raise AssertionError("debio relanzar")
    except RuntimeError:
        pass
    assert "coalesce:job" not in client.store  # liberado para el reintento
    assert len(calls) == 1


def test_redis_down_is_fail_open(monkeypatch):
    _patch_client(monkeypatch, FakeRedis(raises=True))
    calls = []

    @_coalesce_on_success("job", 60)
    def job():
        calls.append(1)
        return {"status": "ok"}

    assert job()["status"] == "ok"
    assert job()["status"] == "ok"  # sin marca posible: ejecuta siempre
    assert len(calls) == 2


def test_window_callable_and_key_parts(monkeypatch):
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
    assert news(scope="tracked")["status"] == "skipped"
    marks = [c for c in client.set_calls if c[1] == "done"]
    assert marks == [
        ("coalesce:news:tracked", "done", False, 25),
        ("coalesce:news:all", "done", False, 500),
    ]
