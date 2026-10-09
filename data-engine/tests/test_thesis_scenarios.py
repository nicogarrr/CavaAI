"""Lector de escenarios: linaje, aislamiento, ausencia de efectos y versiones."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.thesis_scenarios import router
from app.core.database import Base, get_db
from app.models import Company, Tenant, ThesisProjectionYear, ValuationModel
from app.services.thesis_projection_service import MODEL_TYPE, MODEL_VERSION, SCENARIOS
from app.services.thesis_scenario_service import ThesisScenarioService

CUTOFF = date(2026, 10, 8)


def trace():
    fact = {"valor": 100, "ejercicio": 2024, "etiqueta": "OFICIAL",
            "fuente_url": "https://www.sec.gov/fixture", "fuente_fecha": "2025-02-01"}
    growth = {"valor": 0.1, "etiqueta": "OFICIAL", "base": "Tasa oficial guardada",
              "fuente_url": "https://www.sec.gov/fixture", "fuente_fecha": "2025-02-01"}
    margin = {"valor": 0.2, "etiqueta": "INFERIDO", "base": "margen FCF derivado de facts FY2024"}
    rows = [{"ejercicio": year, "ingresos": 110, "fcf": 22, "bps": 1.1,
             "crecimiento": growth, "margen_fcf": margin} for year in (2025, 2026)]
    return {"model_type": MODEL_TYPE, "model_version": MODEL_VERSION, "as_of": CUTOFF.isoformat(),
            "base": {key: deepcopy(fact) for key in ("ingresos", "fcf", "resultado_neto", "acciones")},
            "escenarios": {s: {"proyecciones": deepcopy(rows)} for s in SCENARIOS}}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, external_id="one"), Tenant(id=2, external_id="two"),
                         Company(id=1, ticker="TEST", name="Prueba", exchange="NASDAQ", company_type="large_cap", valuation_model="dcf")])
        session.commit()
        session.info["tenant_id"] = 1
        yield session
    engine.dispose()


def save(db, payload=None, version=1, years=True):
    payload = trace() if payload is None else payload
    model = ValuationModel(company_id=1, model_type=MODEL_TYPE, version=version, calculation_trace=payload)
    db.add(model)
    db.flush()
    if years:
        for s in SCENARIOS:
            for r in payload["escenarios"][s]["proyecciones"]:
                db.add(ThesisProjectionYear(company_id=1, valuation_model_id=model.id, scenario=s,
                       fiscal_year=r["ejercicio"], revenue=Decimal(str(r["ingresos"])),
                       fcf=Decimal(str(r["fcf"])), eps=Decimal(str(r["bps"])), label="INFERIDO",
                       source="proyeccion determinista guardada", as_of=CUTOFF, day=CUTOFF))
    db.commit()
    return model


def read(db):
    with db.no_autoflush:
        return ThesisScenarioService().read(db, db.get(Company, 1))


def test_read_only_exact_values_and_labels(db, monkeypatch):
    save(db)
    from app.services.thesis_projection_service import ThesisProjectionService
    monkeypatch.setattr(ThesisProjectionService, "project", lambda *a, **kw: pytest.fail("No recalcular"))
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda c, cur, sql, params, ctx, many: statements.append(sql))
    value = read(db)
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    for scenario in SCENARIOS:
        row = value["escenarios"][scenario]["proyecciones"][0]
        for key, expected in (("ingresos", 110), ("fcf", 22), ("bps", 1.1)):
            assert row[key]["valor"] == expected
            assert row[key]["etiqueta"] == "INFERIDO"
            assert row[key]["fuente"]["fila_id"]
            assert row[key]["fecha"] == CUTOFF.isoformat()
        assert value["escenarios"][scenario]["precio_objetivo_5y"]["etiqueta"] == "N/D"
    assert read(db) == value
    assert db.scalar(select(func.count(ValuationModel.id))) == 1


def test_empty_no_old_version_fallback(db):
    assert read(db)["estado"] == "N/D"
    save(db)
    save(db, version=2, years=False)
    result = read(db)
    assert result["fuente"]["version"] == 2
    assert result["estado"] == "N/D"
    assert all(not s["proyecciones"] for s in result["escenarios"].values())


def test_cross_tenant_and_missing_context(db):
    save(db)
    db.info["tenant_id"] = 2
    assert read(db)["estado"] == "N/D"
    del db.info["tenant_id"]
    with pytest.raises(ValueError, match="contexto"):
        read(db)


@pytest.mark.parametrize("change", ["llm_growth", "llm_margin", "no_source", "future_source", "unknown_version"])
def test_fail_closed_provenance(db, change):
    payload = trace()
    if change == "llm_growth":
        payload["escenarios"]["base"]["proyecciones"][0]["crecimiento"].update(
            {"base": "asuncion de driver del modelo", "etiqueta": "INFERIDO"})
    elif change == "llm_margin":
        payload["escenarios"]["base"]["proyecciones"][0]["margen_fcf"]["base"] = "input inferido documentado: LLM"
    elif change == "no_source":
        payload["base"]["ingresos"]["fuente_url"] = None
    elif change == "future_source":
        payload["base"]["ingresos"]["fuente_fecha"] = "2099-01-01"
    else:
        payload["model_version"] = "future-version"
    save(db, payload)
    rows = read(db)["escenarios"]["base"]["proyecciones"]
    metric = "fcf" if change == "llm_margin" else "ingresos"
    assert rows[0][metric]["valor"] is None
    assert rows[0][metric]["motivo"]
    if change == "llm_growth":
        assert rows[1][metric]["valor"] is None  # contaminacion acumulada
    if change == "llm_margin":
        assert rows[0]["ingresos"]["valor"] == 110  # bloqueo acotado


def test_table_trace_mismatch_and_null(db):
    save(db)
    row = db.scalar(select(ThesisProjectionYear).where(ThesisProjectionYear.scenario == "base"))
    row.revenue = Decimal("999")
    row.fcf = None
    db.commit()
    result = read(db)["escenarios"]["base"]["proyecciones"][0]
    assert result["ingresos"]["valor"] is None
    assert "no coincide" in result["ingresos"]["motivo"]
    assert result["fcf"]["valor"] is None
    assert result["bps"]["valor"] == 1.1


def test_no_autoflush_pending_changes(db):
    save(db)
    pending = ValuationModel(company_id=1, model_type=MODEL_TYPE, version=99)
    db.add(pending)
    assert read(db)["fuente"]["version"] == 1
    assert pending.id is None


def test_http_and_spanish_errors(db):
    app = FastAPI()
    app.include_router(router, prefix="/companies")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    assert client.get("/companies/TEST/thesis-scenarios").status_code == 200
    assert client.get("/companies/MISSING/thesis-scenarios").json()["detail"] == "Empresa no encontrada."
    db.info.pop("tenant_id")
    assert client.get("/companies/TEST/thesis-scenarios").status_code == 403


@pytest.mark.parametrize("damage", ["missing_year", "duplicate_year", "date_mismatch", "label"])
def test_corrupt_snapshot_is_not_published(db, damage):
    payload = trace()
    if damage == "missing_year":
        payload["escenarios"]["base"]["proyecciones"].pop(0)
    elif damage == "duplicate_year":
        payload["escenarios"]["base"]["proyecciones"].append(
            deepcopy(payload["escenarios"]["base"]["proyecciones"][0]))
    # Duplicated trace years cannot be inserted into the table (unique constraint).
    saved = save(db, years=False)
    db.add(ThesisProjectionYear(company_id=1, valuation_model_id=saved.id, scenario="base",
           fiscal_year=2026, revenue=Decimal("110"), fcf=Decimal("22"), eps=Decimal("1.1"),
           label="N/D" if damage == "label" else "INFERIDO", source="guardado",
           as_of=date(2026, 10, 7) if damage == "date_mismatch" else CUTOFF, day=CUTOFF))
    db.commit()
    # One table row is enough to check the complete upstream chain in the trace.
    saved.calculation_trace = payload
    db.commit()
    row = read(db)["escenarios"]["base"]["proyecciones"][0]
    assert row["ingresos"]["valor"] is None
    assert row["ingresos"]["motivo"]


@pytest.mark.parametrize("historic_source", ["LLM", "SEC"])
def test_real_producer_cagr_extremes_lack_persisted_lineage(db, monkeypatch, historic_source):
    from datetime import UTC, datetime

    from app.models import Document, FinancialFact
    from app.services.thesis_projection_service import ThesisProjectionService
    from app.services.valuation_service import ValuationService

    monkeypatch.setattr(ValuationService, "value_company", lambda *a, **kw: {
        "bear_value": 40.0, "base_value": 50.0, "bull_value": 65.0,
        "publishable": True, "publication_blockers": [],
    })
    doc = Document(company_id=1, title="Resultados oficiales", source_type="primary_official",
                   source_url="https://www.sec.gov/fixture",
                   published_at=datetime(2025, 2, 1, tzinfo=UTC))
    db.add(doc)
    db.flush()
    for year, value in ((2022, 64), (2023, 80), (2024, 100)):
        official = year == 2024 or historic_source == "SEC"
        db.add(FinancialFact(company_id=1, metric="revenue", value=Decimal(value), unit="USD",
                            period=f"{year}-12-31:FY", fiscal_year=year,
                            source_type="SEC" if official else "LLM",
                            source_id=doc.id if official else None))
    for metric, value in (("free_cash_flow", 20), ("net_income", 10), ("shares_diluted", 10)):
        db.add(FinancialFact(company_id=1, metric=metric, value=Decimal(value), unit="USD",
                            period="2024-12-31:FY", fiscal_year=2024,
                            source_type="SEC", source_id=doc.id))
    db.commit()
    company = db.get(Company, 1)
    producer = ThesisProjectionService()
    payload = producer.project(db, company, as_of=CUTOFF)
    assert payload["base"]["ingresos"]["etiqueta"] == "OFICIAL"
    projected = payload["escenarios"]["base"]["proyecciones"][0]
    assert projected["crecimiento"]["valor"] == pytest.approx(0.25)
    assert projected["crecimiento"]["base"].startswith("CAGR")
    assert projected["ingresos"] == pytest.approx(125)
    producer.persist(db, company, payload)
    # The real project/persist path loses endpoint provenance in both cases.
    # Current facts are not a substitute for the immutable saved lineage.
    view = read(db)
    for scenario in SCENARIOS:
        for row in view["escenarios"][scenario]["proyecciones"]:
            for metric in ("ingresos", "fcf", "bps"):
                assert row[metric]["valor"] is None
                assert row[metric]["etiqueta"] == "N/D"
                assert "extremos historicos" in row[metric]["motivo"]


def test_cagr_prefix_alone_cannot_authorize_snapshot(db):
    payload = trace()
    for scenario in SCENARIOS:
        for row in payload["escenarios"][scenario]["proyecciones"]:
            row["crecimiento"] = {"valor": 0.1, "etiqueta": "INFERIDO",
                                   "base": "CAGR de ingresos FY2022-FY2024 sobre facts anuales"}
    save(db, payload)
    assert read(db)["escenarios"]["base"]["proyecciones"][0]["ingresos"]["valor"] is None
