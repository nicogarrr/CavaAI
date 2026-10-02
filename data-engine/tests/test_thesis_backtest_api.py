"""API del backtest: el contrato de honestidad, no solo el de codigo HTTP.

Dos reglas atraviesan los cuatro endpoints y se comprueban aqui porque son las
que un cliente no puede deducir solo leyendo el JSON:

- **Ningun fair value sin su corte.** Un numero de tesis sin ``as_of`` y
  ``evidence_cutoff`` al lado es justo el dato que el backtest existe para
  impedir mostrar.
- **La rejilla no se ejecuta en el request.** Se encola y se responde 202, con
  el estado real del envelope de jobs.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.api.routes import thesis_backtest as backtest_routes
from app.core.database import get_db
from app.models.thesis_backtest import STATUS_INSUFFICIENT_DATA, STATUS_OK
from app.services.thesis_backtest_job_service import MAX_CELLS
from tests.backtest_fixtures import TICKER, make_session, seed_company


@pytest.fixture
def client():
    session = make_session()
    seed_company(session)
    app = APIRouter()
    app.include_router(backtest_routes.router, prefix="/api/thesis-backtest")
    from fastapi import FastAPI

    http_app = FastAPI()
    http_app.include_router(app)

    def override_db():
        yield session

    http_app.dependency_overrides[get_db] = override_db
    with TestClient(http_app) as test_client:
        test_client.session = session  # type: ignore[attr-defined]
        yield test_client
    session.close()


def _seed_run(session, tickers=(TICKER,), start=date(2025, 1, 1), end=date(2025, 6, 30)):
    from app.services.thesis_backtest_service import ThesisBacktestService

    return ThesisBacktestService().run(
        session, tickers=list(tickers), start=start, end=end, step="1M"
    ).id


# ----------------------------------------------------------------- contrato


def test_router_exposes_the_four_documented_endpoints():
    """The router is mounted under ``/api/thesis-backtest`` by the app wiring.

    The paths here are router-relative on purpose: this test does not need the
    central router, and asserting on its prefix would couple D1 to a file it must
    not edit.
    """
    paths = {route.path for route in backtest_routes.router.routes}
    assert paths == {"", "/{run_id}", "/{run_id}/report", "/{run_id}/cells"}
    methods = {
        (route.path, method)
        for route in backtest_routes.router.routes
        for method in route.methods
    }
    assert ("", "POST") in methods
    assert ("/{run_id}", "GET") in methods
    assert ("/{run_id}/report", "GET") in methods
    assert ("/{run_id}/cells", "GET") in methods


def test_launch_returns_202_with_parameters_and_the_cell_grid(client):
    response = client.post(
        "/api/thesis-backtest",
        json={"tickers": [TICKER], "start": "2025-01-01", "end": "2025-06-30", "step": "1M"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["tickers"] == [TICKER]
    assert body["step"] == "1M"
    assert body["as_of_strategy"] == "replay"
    assert body["celdas_planificadas"] == 6
    assert body["cortes"][0] == "2025-01-31"
    assert body["status"] in {"queued", "running", "dispatch_failed", "succeeded"}
    # No ETA: the repo's contract is honest state, never a prediction.
    assert "eta" not in body and "ETA" not in body
    assert "Sin ETA estimada" in body["nota"]


def test_launch_is_idempotent_for_the_same_grid(client):
    payload = {"tickers": [TICKER], "start": "2025-01-01", "end": "2025-06-30"}
    first = client.post("/api/thesis-backtest", json=payload).json()
    second = client.post("/api/thesis-backtest", json=payload).json()
    assert first["run_id"] == second["run_id"]
    assert second["created"] is False


def test_launch_rejects_an_inverted_range(client):
    response = client.post(
        "/api/thesis-backtest",
        json={"tickers": [TICKER], "start": "2025-06-30", "end": "2025-01-01"},
    )
    assert response.status_code == 400
    assert "start es posterior a end" in response.json()["detail"]


def test_launch_rejects_an_unknown_step(client):
    response = client.post(
        "/api/thesis-backtest",
        json={"tickers": [TICKER], "start": "2025-01-01", "end": "2025-06-30", "step": "1W"},
    )
    assert response.status_code == 422


def test_launch_rejects_a_non_replay_strategy(client):
    """Una estrategia que no reproduce el pasado no es un backtest."""
    response = client.post(
        "/api/thesis-backtest",
        json={
            "tickers": [TICKER],
            "start": "2025-01-01",
            "end": "2025-06-30",
            "as_of_strategy": "look_forward",
        },
    )
    assert response.status_code == 422


def test_launch_rejects_an_index_as_a_thesis(client):
    """Un indice es la referencia del alpha, no algo que tenga tesis."""
    response = client.post(
        "/api/thesis-backtest",
        json={"tickers": ["^GSPC"], "start": "2025-01-01", "end": "2025-06-30"},
    )
    assert response.status_code == 400
    assert "indice de referencia" in response.json()["detail"]


def test_launch_refuses_an_oversized_grid_instead_of_queueing_it(client):
    """Decir "son 4800 celdas, lodiremos" antes, no descubrirlo tres horas despues."""
    response = client.post(
        "/api/thesis-backtest",
        json={
            "tickers": [f"T{index:02d}" for index in range(40)],
            "start": "2015-01-01",
            "end": "2025-12-31",
            "step": "1M",
        },
    )
    assert response.status_code == 400
    assert f"maximo de {MAX_CELLS}" in response.json()["detail"]


# ------------------------------------------------------------------ lectura


def test_status_reports_cells_by_state(client):
    run_id = _seed_run(client.session)
    body = client.get(f"/api/thesis-backtest/{run_id}").json()
    assert body["run_id"] == run_id
    assert body["estado"] == "succeeded"
    assert body["celdas"]["hechas"] == 6
    assert STATUS_OK in body["celdas"]["por_estado"]
    assert body["rango"] == {"start": "2025-01-01", "end": "2025-06-30"}


def test_status_404s_on_an_unknown_run(client):
    assert client.get("/api/thesis-backtest/999999").status_code == 404


def test_report_answers_the_product_question(client):
    run_id = _seed_run(client.session)
    body = client.get(f"/api/thesis-backtest/{run_id}/report").json()
    assert body["run_id"] == run_id
    assert body["celdas"]["total"] == 6
    assert "hit_rate_1A" in body
    assert "retornos_realizados" in body
    assert "dispersion" in body
    assert "rechazos_lookahead" in body
    assert body["advertencias"]
    # The verdict must be a sentence a reader can be held to, not a bare number.
    assert isinstance(body["advertencias"][0], str)
    assert len(body["advertencias"][0]) > 40


def test_report_404s_on_an_unknown_run(client):
    assert client.get("/api/thesis-backtest/424242/report").status_code == 404


def test_cells_never_return_a_fair_value_without_its_cutoff(client):
    run_id = _seed_run(client.session)
    body = client.get(f"/api/thesis-backtest/{run_id}/cells").json()
    assert body["total"] == 6
    for row in body["celdas"]:
        assert "as_of" in row and "evidence_cutoff" in row
        assert row["as_of"] == row["evidence_cutoff"]
        assert "model_version" in row
        assert "cell_hash" in row


def test_cells_separate_price_from_fair_value(client):
    """El precio de ese dia es un hecho; el fair value es una opinion.

    Mantenerlos en campos distintos es lo que impide que un cliente rellene una
    celda de abstencion con el precio y publishes un retorno que no existe.
    """
    run_id = _seed_run(client.session)
    body = client.get(f"/api/thesis-backtest/{run_id}/cells").json()
    for row in body["celdas"]:
        assert "precio_actual" in row
        if row["estado"] != STATUS_OK:
            assert row["fair_value"] is None
            assert row["nota"].startswith("N/D")
        else:
            assert row["fair_value"] is not None


def test_cells_can_be_filtered_by_ticker_and_date(client):
    run_id = _seed_run(client.session)
    by_ticker = client.get(f"/api/thesis-backtest/{run_id}/cells?ticker={TICKER}").json()
    assert by_ticker["filtros"]["ticker"] == TICKER
    assert by_ticker["total"] == 6

    by_date = client.get(
        f"/api/thesis-backtest/{run_id}/cells?as_of=2025-06-30"
    ).json()
    assert by_date["filtros"]["as_of"] == "2025-06-30"
    assert by_date["total"] == 1
    assert by_date["celdas"][0]["as_of"] == "2025-06-30"


def test_cells_are_paged(client):
    run_id = _seed_run(client.session)
    body = client.get(f"/api/thesis-backtest/{run_id}/cells?limit=2").json()
    assert body["limit"] == 2
    assert body["devueltas"] == 2
    assert body["total"] == 6


def test_cells_reject_an_unbounded_limit(client):
    run_id = _seed_run(client.session)
    assert (
        client.get(f"/api/thesis-backtest/{run_id}/cells?limit=100000").status_code == 422
    )


def test_abstention_cell_reports_its_reason_in_spanish(client):
    """Una celda sin fair value dice por que, en el idioma del repo."""
    from app.services.thesis_backtest_service import ThesisBacktestService

    session = client.session
    run_id = ThesisBacktestService().run(
        session, tickers=[TICKER], start=date(2024, 1, 1), end=date(2024, 3, 31)
    ).id
    body = client.get(f"/api/thesis-backtest/{run_id}/cells").json()
    statuses = {row["estado"] for row in body["celdas"]}
    assert statuses <= {STATUS_INSUFFICIENT_DATA, STATUS_OK, "not_yet_published"}
    for row in body["celdas"]:
        assert row["fair_value"] is None or row["estado"] == STATUS_OK
        if row["estado"] != STATUS_OK:
            assert row["degradada_motivo"]
