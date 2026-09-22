"""TaxReportService contracts: FIFO lots, FX honesty, dividend grouping.

The tax report feeds an IRPF-style filing: a silently wrong number is worse
than a missing one. These contracts pin FIFO cost basis (including across
fiscal years), per-company dividend/withholding grouping, conversion at the
payment-date FX rate, and explicit incomplete states when no FX rate exists
- never a par conversion.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, FXRate, Portfolio, Transaction
from app.services.tax_report_service import TaxReportService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _tx(db, company, day, action, qty, price, currency="EUR", fees="0"):
    db.add(Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal(fees), currency=currency,
    ))
    db.commit()


def _eur_portfolio(db):
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    db.commit()


def test_fifo_consumes_oldest_lots_first(db):
    _eur_portfolio(db)
    c = _company(db, "AAA")
    _tx(db, c, date(2026, 1, 10), "buy", 10, 100)
    _tx(db, c, date(2026, 2, 10), "buy", 10, 120)
    _tx(db, c, date(2026, 6, 1), "sell", 15, 200)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "AAA")
    assert row["proceeds_native"] == 3000.0
    assert row["cost_native"] == 1600.0  # 10x100 + 5x120
    assert row["gain_native"] == 1400.0


def test_cost_basis_spans_fiscal_years(db):
    _eur_portfolio(db)
    c = _company(db, "BBB")
    _tx(db, c, date(2025, 6, 1), "buy", 10, 100)
    _tx(db, c, date(2026, 3, 1), "sell", 10, 150)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "BBB")
    assert row["cost_native"] == 1000.0
    assert row["gain_native"] == 500.0
    assert report["summary"]["sell_count"] == 1


def test_dividend_and_withholding_grouped_per_company(db):
    _eur_portfolio(db)
    c = _company(db, "CCC")
    _tx(db, c, date(2026, 4, 1), "dividend", 100, 100)
    _tx(db, c, date(2026, 4, 1), "withholding", -19, 19)
    report = TaxReportService().compute_report(db, 2026)
    row = next(d for d in report["dividends"] if d["ticker"] == "CCC")
    assert row["dividends_base"] == 100.0
    assert row["withholding_base"] == 19.0
    assert {p["type"] for p in row["payments"]} == {"dividend", "withholding"}


def test_foreign_dividend_converted_at_payment_date_rate(db):
    _eur_portfolio(db)
    c = _company(db, "DDD")
    db.add(FXRate(base_currency="EUR", quote_currency="USD",
                  rate_date=date(2026, 3, 1), rate=Decimal("0.90"), source="test"))
    db.add(FXRate(base_currency="EUR", quote_currency="USD",
                  rate_date=date(2026, 5, 1), rate=Decimal("0.95"), source="test"))
    db.commit()
    _tx(db, c, date(2026, 4, 15), "dividend", 100, 100, currency="USD")
    report = TaxReportService().compute_report(db, 2026)
    row = next(d for d in report["dividends"] if d["ticker"] == "DDD")
    assert row["dividends_native"] == 100.0
    assert row["dividends_base"] == 90.0  # latest rate on/before 2026-04-15


def test_missing_fx_dividend_is_explicit_never_par(db):
    _eur_portfolio(db)
    c = _company(db, "EEE")
    _tx(db, c, date(2026, 4, 15), "dividend", 100, 100, currency="USD")
    report = TaxReportService().compute_report(db, 2026)
    row = next(d for d in report["dividends"] if d["ticker"] == "EEE")
    assert row["dividends_base"] is None
    assert row["missing_fx"] is True
    assert report["summary"]["incomplete_fx"] is True
    assert "EEE" in report["summary"]["missing_fx"]
    assert report["summary"]["total_dividends_base"] is None


def test_missing_fx_realized_gain_reports_none(db):
    _eur_portfolio(db)
    c = _company(db, "FFF")
    _tx(db, c, date(2026, 1, 10), "buy", 10, 100, currency="USD")
    _tx(db, c, date(2026, 6, 1), "sell", 10, 150, currency="USD")
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "FFF")
    assert row["gain_native"] == 500.0
    assert row["gain_base"] is None
    assert report["summary"]["incomplete_fx"] is True
