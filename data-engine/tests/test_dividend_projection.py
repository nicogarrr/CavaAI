"""Tests de la proyección mes a mes de dividendos con retenciones."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    DividendRecord,
    FXRate,
    Portfolio,
    Position,
)
from app.services.dividend_projection_service import DividendProjectionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db, ticker="AAPL", currency="USD", country="US"):
    company = Company(
        ticker=ticker,
        name=ticker,
        exchange="NASDAQ",
        currency=currency,
        sector="Tech",
        industry="Tech",
        company_type="holding",
        valuation_model="unassigned",
        domicile_country=country,
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _position(db, company, quantity="10", currency="USD"):
    portfolio = Portfolio(name="p", base_currency="EUR")
    db.add(portfolio)
    db.commit()
    position = Position(
        portfolio_id=portfolio.id,
        company_id=company.id,
        quantity=Decimal(quantity),
        average_cost=Decimal("150"),
        market_price=Decimal("200"),
        market_value=Decimal("2000"),
        currency=currency,
    )
    db.add(position)
    db.commit()
    return position


def _dividend(db, company, ex_date, amount, currency="USD", pay_date=None):
    record = DividendRecord(
        company_id=company.id,
        ex_date=ex_date,
        pay_date=pay_date,
        amount=Decimal(str(amount)),
        currency=currency,
        source="yahoo",
    )
    db.add(record)
    db.commit()
    return record


def _fx(db, quote="USD", base="EUR", rate="0.9"):
    db.add(
        FXRate(
            base_currency=base,
            quote_currency=quote,
            rate_date=date.today(),
            rate=Decimal(rate),
        )
    )
    db.commit()


def test_quarterly_payer_projects_same_amounts_next_year(db):
    company = _company(db)
    _position(db, company)
    today = date.today()
    for days_ago in (15, 105, 195, 285):
        _dividend(db, company, today - timedelta(days=days_ago), "0.25")
    _fx(db)

    out = DividendProjectionService().project(db, months=12)

    assert out["label"] == "INFERIDO"
    assert out["coverage"]["with_data"] == 1
    assert out["coverage"]["sin_datos"] == []
    pos = out["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["frequency_last_year"] == 4
    # 4 dividendos x 0.25 x 10 acciones = 10 USD brutos proyectados.
    assert pos["gross_year_native"] == pytest.approx(10.0)
    # En base EUR (fx 0.9): 9.0 bruto, origen 15% -> 1.35 retenido.
    assert pos["gross_year_base"] == pytest.approx(9.0)
    assert pos["source_withheld_year_base"] == pytest.approx(1.35)
    month_sum = sum(m["gross_base"] for m in out["months"])
    assert month_sum == pytest.approx(9.0)


def test_position_without_records_is_sin_datos_never_zero(db):
    company = _company(db, ticker="XYZ")
    _position(db, company)
    _fx(db)

    out = DividendProjectionService().project(db, months=12)

    assert out["coverage"]["with_data"] == 0
    assert out["coverage"]["sin_datos"] == ["XYZ"]
    assert all(m["gross_base"] == 0.0 for m in out["months"])
    assert out["positions"] == []


def test_irpf_progressive_and_double_taxation_floor(db):
    company = _company(db)
    _position(db, company, quantity="100000")
    today = date.today()
    _dividend(db, company, today - timedelta(days=60), "1.00")
    _dividend(db, company, today - timedelta(days=200), "1.00")
    _fx(db, rate="1.0")

    out = DividendProjectionService().project(db, months=12)

    # 200.000 EUR brutos: la escala del ahorro supera el 19% en agregado,
    # y la cuota nunca puede quedar negativa por la deducción de origen.
    total_irpf = sum(m["irpf_base"] for m in out["months"])
    total_source = sum(m["source_withheld_base"] for m in out["months"])
    total_net = sum(m["net_base"] for m in out["months"])
    total_gross = sum(m["gross_base"] for m in out["months"])
    assert total_gross == pytest.approx(200000.0)
    assert total_irpf > 200000.0 * 0.19
    assert total_source == pytest.approx(30000.0)
    for m in out["months"]:
        assert m["net_base"] <= m["gross_base"]
        assert m["net_base"] >= 0.0
    assert total_net == pytest.approx(total_gross - max(total_irpf, total_source))


def test_unknown_country_withholding_is_none_never_zero(db):
    company = _company(db, ticker="NSR", country="JP")
    _position(db, company)
    today = date.today()
    _dividend(db, company, today - timedelta(days=100), "5.00")
    _fx(db)

    out = DividendProjectionService().project(db, months=12)

    pos = out["positions"][0]
    assert pos["source_withholding_rate"] is None
    assert pos["source_withheld_year_base"] is None
    assert out["coverage"]["unknown_source_withholding"] == ["NSR"]


def test_currency_mismatch_records_are_skipped(db):
    company = _company(db, ticker="GBPAY", currency="GBP", country="GB")
    _position(db, company, currency="GBP")
    today = date.today()
    # Declarado en USD pero la posición valora en GBP: no se usa.
    _dividend(db, company, today - timedelta(days=50), "1.00", currency="USD")

    out = DividendProjectionService().project(db, months=12)

    assert out["coverage"]["sin_datos"] == ["GBPAY"]
    assert out["positions"] == []


def test_missing_fx_excludes_base_aggregation(db):
    company = _company(db, ticker="NOFX", country="US")
    _position(db, company)
    today = date.today()
    _dividend(db, company, today - timedelta(days=70), "2.00")
    # Sin FXRate USD->EUR.

    out = DividendProjectionService().project(db, months=12)

    assert out["coverage"]["fx_missing"] == ["NOFX"]
    assert out["positions"][0]["gross_year_base"] is None
    assert all(m["gross_base"] == 0.0 for m in out["months"])
