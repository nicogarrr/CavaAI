"""Semilla test-only de precios (POST /api/market/prices/seed)."""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.models import Company, MarketPrice
from tests.auth_helpers import bound_headers

SECRET = "market-prices-seed-test-secret-at-least-32"


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_AUTH_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _post_seed(client: TestClient, items: list[dict]):
    body = json.dumps({"items": items}).encode()
    return client.post(
        "/api/market/prices/seed",
        content=body,
        headers={
            **bound_headers(SECRET, "seed-tenant", "seed-user", method="POST", path="/api/market/prices/seed", body=body),
            "Content-Type": "application/json",
        },
    )


def test_seed_inserta_y_actualiza_cierres(settings_env, monkeypatch):
    import app.api.routes.market as market_routes
    monkeypatch.setattr(market_routes, "get_settings", lambda: type("S", (), {"is_production": False})())
    init_db()
    client = TestClient(main.app)
    res = _post_seed(client, [
        {"ticker": "SEEDCOST", "date": "2026-09-24", "close": "100", "volume": 1000},
        {"ticker": "SEEDCOST", "date": "2026-09-25", "close": "110", "volume": 2000},
    ])
    assert res.status_code == 200, res.text
    assert res.json() == {"seeded": 2}

    db = SessionLocal()
    rows = db.scalars(
        select(MarketPrice).join(Company).where(Company.ticker == "SEEDCOST")
    ).all()
    assert len(rows) == 2
    assert all(row.adj_close is None for row in rows)  # el seed no afirma ajuste por splits
    assert all(row.source == "e2e-seed" for row in rows)

    # Idempotente por (company, date): actualiza, no duplica.
    res = _post_seed(client, [{"ticker": "SEEDCOST", "date": "2026-09-25", "close": "120", "volume": 3000}])
    assert res.status_code == 200, res.text
    db.expire_all()  # la sesion ya tenia las filas cargadas: releer de BD
    rows = db.scalars(select(MarketPrice).join(Company).where(Company.ticker == "SEEDCOST")).all()
    assert len(rows) == 2
    assert max(row.close for row in rows) == Decimal("120")
    db.close()


def test_seed_no_existe_en_produccion(settings_env, monkeypatch):
    import app.api.routes.market as market_routes
    monkeypatch.setattr(market_routes, "get_settings", lambda: type("S", (), {"is_production": True})())
    client = TestClient(main.app)
    res = _post_seed(client, [{"ticker": "SEEDNFLX", "date": "2026-09-25", "close": "90"}])
    assert res.status_code == 404
