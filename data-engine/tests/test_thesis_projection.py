"""PR A: proyeccion determinista de tesis a 5 ejercicios (sin LLM)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.thesis_projection import router
from app.core.database import Base, get_db
from app.models import (
    Company,
    FinancialFact,
    MarketPrice,
    Tenant,
    ThesisProjectionYear,
    ValuationModel,
    ValuationOutput,
)
from app.services import thesis_projection_service as svc_module
from app.services.thesis_projection_service import ThesisProjectionService
from app.services.valuation_service import ValuationService
from app.valuation.point_in_time import LookaheadError

AS_OF = date(2026, 10, 9)
FAKE_VALUATION = {"bear_value": 40.0, "base_value": 50.0, "bull_value": 65.0}


def fake_value_company(self, db, company, *, as_of=None):  # noqa: ARG001
    """Valor por accion actual fijo: el DCF real se prueba en su propio suite."""
    return dict(FAKE_VALUATION)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [Tenant(id=1, external_id="a"), Tenant(id=2, external_id="b")]
        )
        session.commit()
        session.info["tenant_id"] = 1
        session.add_all(
            [
                Company(
                    id=1,
                    ticker="TEST",
                    name="Test Co",
                    exchange="NASDAQ",
                    company_type="large_cap",
                    valuation_model="dcf",
                ),
                Company(
                    id=2,
                    ticker="EMPTY",
                    name="Sin Datos",
                    exchange="NASDAQ",
                    company_type="large_cap",
                    valuation_model="dcf",
                ),
            ]
        )
        for year, revenue in ((2022, 64.0), (2023, 80.0), (2024, 100.0)):
            session.add(
                FinancialFact(
                    company_id=1,
                    metric="revenue",
                    value=Decimal(str(revenue)),
                    unit="USD",
                    period=f"{year}-FY",
                    fiscal_year=year,
                    source_type="SEC",
                )
            )
        for metric, value in (
            ("free_cash_flow", 20.0),
            ("net_income", 10.0),
            ("shares_diluted", 10.0),
        ):
            session.add(
                FinancialFact(
                    company_id=1,
                    metric=metric,
                    value=Decimal(str(value)),
                    unit="USD",
                    period="2024-FY",
                    fiscal_year=2024,
                    source_type="SEC",
                )
            )
        session.add(
            MarketPrice(
                company_id=1,
                date=date(2026, 10, 8),
                close=Decimal("100"),
                source="seed",
            )
        )
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def valued(monkeypatch):
    monkeypatch.setattr(ValuationService, "value_company", fake_value_company)
    return monkeypatch


def project(db, ticker_id=1):
    company = db.get(Company, ticker_id)
    return ThesisProjectionService().project(db, company, as_of=AS_OF)


def client_for(db):
    app = FastAPI()
    app.include_router(router, prefix="/companies")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_projection_is_deterministic_and_labelled(db, valued):
    payload = project(db)
    assert payload["ejercicio_base"] == 2024
    assert payload["disclaimer"] == svc_module.DISCLAIMER_ES
    base = payload["escenarios"]["base"]["proyecciones"]
    assert [row["ejercicio"] for row in base] == [2025, 2026, 2027, 2028, 2029]
    # CAGR 2022-2024 = (100/64)^(1/2) - 1 = 0.25 exacto.
    assert base[0]["crecimiento"]["valor"] == pytest.approx(0.25)
    assert base[0]["ingresos"] == pytest.approx(125.0)
    assert base[-1]["ingresos"] == pytest.approx(100.0 * 1.25**5)
    assert base[-1]["fcf"] == pytest.approx(100.0 * 1.25**5 * 0.20)
    assert base[-1]["bps"] == pytest.approx(100.0 * 1.25**5 * 0.10 / 10.0)
    assert base[-1]["etiqueta"] == "INFERIDO"
    assert base[-1]["etiquetas"] == {
        "ingresos": "INFERIDO",
        "fcf": "INFERIDO",
        "bps": "INFERIDO",
    }
    assert "CAGR de ingresos FY2022-FY2024" in base[0]["crecimiento"]["base"]
    assert payload["base"]["ingresos"]["etiqueta"] == "OFICIAL"
    assert payload["base"]["ingresos"]["fuente"] == "SEC FY2024"


def test_scenario_spread_and_burn_rule(db, valued):
    payload = project(db)
    first = {
        s: payload["escenarios"][s]["proyecciones"][0] for s in ("bear", "base", "bull")
    }
    assert first["bear"]["crecimiento"]["valor"] == pytest.approx(0.25 - 0.08)
    assert first["bull"]["crecimiento"]["valor"] == pytest.approx(0.25 + 0.08)
    assert first["bear"]["margen_fcf"]["valor"] == pytest.approx(0.20 - 0.06)
    assert first["bull"]["margen_fcf"]["valor"] == pytest.approx(0.20 + 0.06)
    assert first["bear"]["etiqueta"] == "INFERIDO"


def test_target_price_uses_valuation_service_and_dated_price(db, valued):
    payload = project(db)
    targets = {
        s: payload["escenarios"][s]["precio_objetivo_5y"] for s in ("bear", "base", "bull")
    }
    # ancla FCF/accion = 20/10 = 2; multiplo base = 50/2 = 25.
    assert payload["ancla_precio_objetivo"] == "fcf"
    fcf5_ps = 100.0 * 1.25**5 * 0.20 / 10.0
    assert targets["base"]["valor"] == pytest.approx(fcf5_ps * 25.0)
    assert targets["base"]["etiqueta"] == "INFERIDO"
    assert targets["base"]["precio_actual"] == pytest.approx(100.0)
    assert targets["base"]["precio_fecha"] == "2026-10-08"
    assert targets["base"]["mos"] == pytest.approx(fcf5_ps * 25.0 / 100.0 - 1)
    assert payload["aviso_coherencia"] is None
    assert targets["bear"]["valor"] < targets["base"]["valor"] < targets["bull"]["valor"]


def test_missing_inputs_are_nd_never_zero(db):
    payload = project(db, ticker_id=2)
    assert payload["ejercicio_base"] is None
    for scenario in ("bear", "base", "bull"):
        assert payload["escenarios"][scenario]["proyecciones"] == []
        target = payload["escenarios"][scenario]["precio_objetivo_5y"]
        assert target["valor"] is None and target["etiqueta"] == "N/D"
        assert target["mos"] is None
    assert payload["base"]["ingresos"]["etiqueta"] == "N/D"
    assert payload["ancla_precio_objetivo"] is None


def test_no_lookahead_raises_on_future_facts(db):
    db.add(
        FinancialFact(
            company_id=1,
            metric="revenue",
            value=Decimal("999"),
            unit="USD",
            period="2099-FY",
            fiscal_year=2099,
            source_type="SEC",
        )
    )
    db.commit()
    with pytest.raises(LookaheadError):
        project(db)


def test_tenant_isolation(db, valued):
    assert project(db)["escenarios"]["base"]["proyecciones"] != []
    db.info["tenant_id"] = 2
    payload = project(db)
    # Los facts son del tenant 1: para el tenant 2 la empresa no tiene datos.
    assert payload["escenarios"]["base"]["proyecciones"] == []
    assert payload["base"]["ingresos"]["etiqueta"] == "N/D"


def test_coherence_warning_when_scenarios_invert(db, monkeypatch):
    def inverted(self, db, company, *, as_of=None):  # noqa: ARG001
        return {"bear_value": 900.0, "base_value": 50.0, "bull_value": 40.0}

    monkeypatch.setattr(ValuationService, "value_company", inverted)
    payload = project(db)
    assert payload["aviso_coherencia"] is not None
    assert "bear <= base <= bull" in payload["aviso_coherencia"]


def test_get_endpoint_e2e(db, valued):
    with client_for(db) as client:
        body = client.get("/companies/TEST/thesis-5y").json()
        assert body["ticker"] == "TEST"
        assert set(body["escenarios"]) == {"bear", "base", "bull"}
        assert body["disclaimer"] == svc_module.DISCLAIMER_ES
        assert body["persistido"] is None
        assert client.get("/companies/NOPE/thesis-5y").status_code == 404
    # El GET es calculo puro: no persiste nada.
    assert db.scalar(select(func.count(ValuationModel.id))) == 0


def test_post_persists_and_is_idempotent_per_day(db, valued):
    with client_for(db) as client:
        first = client.post("/companies/TEST/thesis-5y/recalcular")
        assert first.status_code == 201
        body = first.json()
        assert body["persistido"]["version"] == 1
        assert body["persistido"]["status"] == "final"
        second = client.post("/companies/TEST/thesis-5y/recalcular")
        assert second.status_code == 201 and second.json()["persistido"]["version"] == 2
    models = db.scalars(
        select(ValuationModel).where(ValuationModel.model_type == "thesis_5y")
    ).all()
    assert len(models) == 2 and models[0].tenant_id == 1
    outputs = db.scalars(select(ValuationOutput)).all()
    assert {o.scenario for o in outputs} == {"bear", "base", "bull"}
    rows = db.scalars(select(ThesisProjectionYear)).all()
    # 3 escenarios x 5 ejercicios; el segundo POST sustituye, no apila.
    assert len(rows) == 15
    assert {row.label for row in rows} == {"INFERIDO"}
    assert all(row.revenue is not None for row in rows)


def test_post_quota_per_tenant(db, valued, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.thesis_projection.DAILY_RECALC_QUOTA", 1
    )
    with client_for(db) as client:
        assert client.post("/companies/TEST/thesis-5y/recalcular").status_code == 201
        blocked = client.post("/companies/TEST/thesis-5y/recalcular")
        assert blocked.status_code == 429
        assert "cuota diaria" in blocked.json()["detail"]


def test_post_requires_tenant(db, valued):
    db.info.clear()
    with client_for(db) as client:
        assert client.post("/companies/TEST/thesis-5y/recalcular").status_code == 403


def test_persist_skips_outputs_without_target_or_mos(db):
    # Sin ValuationService mockeado el DCF real no tiene inputs suficientes:
    # objetivo N/D -> no se graba ValuationOutput con un 0 silencioso.
    payload = project(db)
    model = ThesisProjectionService().persist(db, 1 and db.get(Company, 1), payload)
    assert model.status == "draft"
    assert db.scalars(select(ValuationOutput)).all() == []
    rows = db.scalars(select(ThesisProjectionYear)).all()
    assert len(rows) == 15
