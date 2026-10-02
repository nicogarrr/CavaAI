"""PR-A/PR-B: wacc y terminal_growth INFERIDOS (base + URLs https) con
procedencia; sin base/URL o fuera de rango siguen fail-closed."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.entities import Base, Company
from app.services.inferred_input_service import (
    InferredInputError,
    InferredInputService,
    validate,
)
from app.services.thesis_provenance import (
    build_inputs_provenance,
    classify_origin,
)
from app.valuation.engines.pre_revenue import _resolve_terminal, _resolve_wacc

BASE = "Dado rf 5,11% (FRED), ERP 4,33% y beta 2,726 (yfinance), inferimos un coste de capital por CAPM"
URLS = ["https://fred.stlouisfed.org/series/DGS10"]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _company(db):
    c = Company(ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", company_type="growth", valuation_model="pre_revenue", factor_tags=["pre_fcf"])
    db.add(c)
    db.commit()
    return c


def test_ranges_and_fail_closed():
    assert validate("wacc", 0.17, BASE, URLS) == []
    assert validate("terminal_growth", 0.025, BASE, URLS) == []
    assert "valor fuera de rango" in validate("wacc", 0.80, BASE, URLS)
    assert "valor fuera de rango" in validate("terminal_growth", 0.09, BASE, URLS)
    assert validate("wacc", 0.17, "corta", URLS)
    assert validate("wacc", 0.17, BASE, [])


def test_create_rejects_without_base(db):
    c = _company(db)
    with pytest.raises(InferredInputError):
        InferredInputService().create(
            db, c, input_key="wacc", value=Decimal("0.17"), base="x", source_urls=URLS
        )


def test_engine_uses_inferred_wacc_and_terminal(db):
    c = _company(db)
    assert _resolve_wacc(db, c) == (0.13, "tag_default")
    assert _resolve_terminal(db, c) == 0.025
    svc = InferredInputService()
    svc.create(db, c, input_key="wacc", value=Decimal("0.17"), base=BASE, source_urls=URLS)
    svc.create(db, c, input_key="terminal_growth", value=Decimal("0.02"), base=BASE, source_urls=URLS)
    assert _resolve_wacc(db, c) == (0.17, "inferred_input")
    assert _resolve_terminal(db, c) == 0.02


def test_provenance_carries_urls_as_inferido():
    model = {
        "assumptions": {
            "wacc": {
                "value": 0.17,
                "unit": "decimal",
                "source_type": "inferred_input",
                "basis": BASE,
                "source_fact_ids": [],
                "confidence": 0.5,
                "source_urls": URLS,
            }
        }
    }
    items = classify_origin(build_inputs_provenance(model), {})
    assert items[0]["origen"] == "INFERIDO"
    assert items[0]["urls_inferencia"] == URLS
    assert items[0]["base_documentada"] is True
