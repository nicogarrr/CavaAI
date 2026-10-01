"""Datos de empresa globales (decision de Nico, opcion A) y rama coherente del
motor pre_revenue: el InferredInput fcf_margin se consulta cuando el snapshot
es coherente y no hay FCF reportado. Las opiniones de usuario siguen aisladas."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base as CoreBase  # noqa: F401  (registra listeners)
from app.models.entities import Base, Company, InferredInput, TenantOwnedMixin
from app.services.inferred_input_service import InferredInputService
from app.valuation.engines.base import ValuationContext
from app.valuation.engines.pre_revenue import PreRevenueScenarioEngine

BASE = "Dado el margen FCF historico de Iridium 2021-2025 con fuentes SEC, inferimos 0,25"
URLS = ["https://www.sec.gov/Archives/edgar/data/1780312/x.htm"]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


class _Snap:
    coherent = True
    as_of_period = "2026-06-30:Q2"
    income_statement = None
    balance_sheet = None
    shares_period = None
    warnings: list = []
    facts: dict = {"revenue": type("F", (), {"confidence": 0.9})()}
    missing_inputs: list = []

    def __init__(self, values):
        self._v = values

    def value(self, metric):
        return self._v.get(metric)

    def fact_ids(self):
        return {}

    def periods(self):
        return {}


VALUES = {"revenue": 70_918_000.0, "shares_diluted": 255_982_592.0, "operating_cash_flow": -71_517_000.0}


def _company(db):
    c = Company(ticker="CUV", name="Cov", exchange="NASDAQ", company_type="growth",
                valuation_model="pre_revenue", factor_tags=["pre_fcf"])
    db.add(c)
    db.commit()
    return c


def _value(db, company, values=None):
    ctx = ValuationContext(db=db, company=company, snapshot=_Snap(values or VALUES),
                           current_price=58.0, engine_key="pre_revenue")
    return PreRevenueScenarioEngine().value(ctx)


def test_inferred_input_is_not_tenant_owned():
    assert not issubclass(InferredInput, TenantOwnedMixin)


def test_inferred_input_visible_from_any_tenant_session(engine):
    with Session(engine) as writer:
        writer.info["tenant_id"] = 2
        company = _company(writer)
        row = InferredInputService().create(
            writer, company, input_key="fcf_margin", value=Decimal("0.25"), base=BASE, source_urls=URLS
        )
        assert row.tenant_id == 2  # autoria informativa
        company_id = company.id
    for tenant in (1, 5, 6, None):
        with Session(engine) as reader:
            if tenant is not None:
                reader.info["tenant_id"] = tenant
            got = InferredInputService().latest_valid(reader, company_id, "fcf_margin")
            assert got is not None and float(got.value) == 0.25


def test_coherent_branch_without_fcf_or_inferred_stays_insufficient(engine):
    with Session(engine) as db:
        company = _company(db)
        result = _value(db, company)
        assert result["status"] == "insufficient_data"
        assert "normalized_fcf_or_fcf_margin" in result["missing_inputs"]


def test_coherent_branch_consults_inferred_margin_and_is_not_publishable(engine):
    with Session(engine) as db:
        db.info["tenant_id"] = 2
        company = _company(db)
        InferredInputService().create(
            db, company, input_key="fcf_margin", value=Decimal("0.25"), base=BASE, source_urls=URLS
        )
    with Session(engine) as other:
        other.info["tenant_id"] = 5
        company = other.scalar(select(Company).where(Company.ticker == "CUV"))
        result = _value(other, company)
        assert result["status"] == "partial"
        assert result["publishable"] is False
        (inferred,) = result["trace"]["inferred_inputs"]
        assert inferred["origen"] == "INFERIDO" and inferred["urls_inferencia"] == URLS
        assert inferred["input_key"] == "fcf_margin" and inferred["inferred_input_id"]
        assert result["base_value"] is not None


def test_coherent_branch_ignores_invalid_inferred_input(engine):
    with Session(engine) as db:
        company = _company(db)
        db.add(InferredInput(company_id=company.id, input_key="fcf_margin", value=Decimal("0.25"),
                             base="corta", source_urls=[]))
        db.commit()
        result = _value(db, company)
        assert result["status"] == "insufficient_data"


def test_reported_fcf_wins_over_inferred(engine):
    with Session(engine) as db:
        company = _company(db)
        InferredInputService().create(
            db, company, input_key="fcf_margin", value=Decimal("0.25"), base=BASE, source_urls=URLS
        )
        values = dict(VALUES, free_cash_flow=-80_000_000.0)
        result = _value(db, company, values)
        assert result["trace"]["inferred_inputs"] == []
