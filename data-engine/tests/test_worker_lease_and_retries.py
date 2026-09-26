"""Los actores de Dramatiq neither retienen leases ni clasifican mal los retries.

Dos fallos, ambos en app/workers/dramatiq_app.py:

1. En los cinco actores con lease, la sesion se abria DESPUES de tomar el lease
   y ANTES del `try`. `_session()` lanza ValueError cuando el tenant no existe o
   no esta activo, y esa excepcion se escapaba sin pasar por el `finally` que
   liberaba el lease: el lease quedaba retenido hasta su TTL. Con los TTL de
   produccion (3.000 s en el pipeline de mercado, 3.600 s en propicks) el
   deadlock era de 50 min y 1 h respectivamente.

2. `_is_transient` miraba `exc.response.status_code`. Los connectors envuelven el
   error de httpx en un RuntimeError plano con el status dentro del mensaje, de
   modo que un 429 o un 503 de SEC/ESEF se clasificaba como permanente y nunca
   se reintentaba. `max_retries=2` estaba muerto justo para los unicos fallos
   para los que existe.
"""

from __future__ import annotations

import inspect

import pytest

from app.workers import dramatiq_app
from app.workers.dramatiq_app import _is_transient, _status_from_message


def _actor_fn(name: str):
    """@dramatiq.actor envuelve la funcion; el codigo real vive en `.fn`."""
    actor = getattr(dramatiq_app, name)
    return getattr(actor, "fn", actor)


# --------------------------------------------------------------------------
# 1. La sesion se abre antes de tomar el lease
# --------------------------------------------------------------------------


LEASED_ACTORS = [
    "refresh_market_pipeline",
    "refresh_portfolio_prices_intraday",
    "refresh_propicks_prices",
    "scan_insider_watchlist",
    "dispatch_insider_alerts",
]


@pytest.mark.parametrize("actor_name", LEASED_ACTORS)
def test_session_is_opened_before_the_lease(actor_name):
    source = inspect.getsource(_actor_fn(actor_name))
    session_at = source.index("_session(")
    lease_at = source.index("acquire_job_lease(")
    assert session_at < lease_at, (
        f"{actor_name}: _session() se abre despues de acquire_job_lease(). Si "
        "_session lanza ValueError (tenant inactivo), el lease se queda "
        "retenido hasta su TTL sin pasar por el finally que lo libera."
    )


@pytest.mark.parametrize("actor_name", LEASED_ACTORS)
def test_lease_held_branch_closes_the_session(actor_name):
    source = inspect.getsource(_actor_fn(actor_name))
    branch_at = source.index("if lease is None:")
    tail = source[branch_at : branch_at + 200]
    assert "db.close()" in tail, (
        f"{actor_name}: la rama 'lease tomado por otro worker' devuelve sin "
        "cerrar la sesion que ya se abrio antes de tomar el lease"
    )


# --------------------------------------------------------------------------
# 2. Los 429/5xx envueltos en RuntimeError se reintentan
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "SEC EDGAR request failed (503 Service Unavailable) for url",
        "SEC fetch failed: Client error '429 Too Many Requests'",
        "ESEF request failed (500)",
        "upstream status 502 Bad Gateway",
    ],
)
def test_wrapped_upstream_status_is_transient(message):
    assert _is_transient(RuntimeError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "unknown_company:AAPL",
        "CIK no resuelto: no such ticker in manifest",
        "ed fiscal year 3000 is out of range",
    ],
)
def test_permanent_messages_stay_permanent(message):
    assert _is_transient(RuntimeError(message)) is False


def test_status_from_message_ignores_non_status_numbers():
    # Un anio, un id o un importe no son un codigo de estado.
    assert _status_from_message("snapshot de 2024 para el informe 2025") is None
    assert _status_from_message("fact 4291 no encontrado") is None
    assert _status_from_message("importe 300000000 sin etiqueta") is None


def test_status_from_message_reads_parenthesised_codes():
    assert _status_from_message("SEC EDGAR request failed (429) for url") == 429
    assert _status_from_message("request failed with HTTP 404") is None


def test_httpx_status_attribute_still_works():
    import httpx

    request = httpx.Request("GET", "https://example.test")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("boom", request=request, response=response)
    assert _is_transient(exc) is True
