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


def test_prior_year_sale_does_not_leak_into_report(db):
    """The FIFO pass needs full history for basis, but a sale from a prior
    fiscal year must never appear in this year's realized totals."""
    _eur_portfolio(db)
    c = _company(db, "ZZ1")
    _tx(db, c, date(2025, 6, 1), "buy", 10, 100)
    _tx(db, c, date(2025, 8, 1), "sell", 10, 150)  # prior-year sale
    _tx(db, c, date(2026, 1, 10), "buy", 10, 100)
    _tx(db, c, date(2026, 3, 1), "sell", 10, 130)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "ZZ1")
    assert report["summary"]["sell_count"] == 1
    assert row["sale_count"] == 1
    assert row["gain_native"] == 300.0  # only the 2026 sale
    assert [s["date"] for s in row["sales"]] == ["2026-03-01"]


def test_wash_sale_repurchase_within_two_months_blocks_and_defers_loss(db):
    """Sell at a loss, repurchase within 2 months: the loss is not computable
    and is deferred onto the repurchase lot's basis, surfacing when that lot
    is sold. Total economic gain is conserved across both sales."""
    _eur_portfolio(db)
    c = _company(db, "WS1")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)   # loss -200
    _tx(db, c, date(2026, 1, 20), "buy", 100, 8)    # repurchase in window
    _tx(db, c, date(2026, 6, 15), "sell", 100, 11)  # sells the deferred lot
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS1")
    first, second = row["sales"]
    assert first["wash_sale_blocked"] is True
    assert first["gain_native"] == 0.0          # loss not computable
    assert first["blocked_loss_native"] == 200.0
    assert first["raw_gain_native"] == -200.0
    # Deferred loss raises the repurchase lot's basis: 800 + 200 = 1000.
    assert second["cost_native"] == 1000.0
    assert second["gain_native"] == 100.0       # 1100 proceeds - 1000 cost
    assert row["gain_native"] == 100.0          # -200 + 300 conserved
    assert row["blocked_loss_native"] == 200.0
    assert report["summary"]["total_blocked_loss_base"] == 200.0
    assert report["summary"]["wash_sale_rule"] == "es-irpf-2m"


def test_wash_sale_repurchase_after_window_lets_loss_compute(db):
    _eur_portfolio(db)
    c = _company(db, "WS2")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)
    _tx(db, c, date(2026, 4, 1), "buy", 100, 8)  # > 2 months after the sale
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS2")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["gain_native"] == -200.0
    assert sale["blocked_loss_native"] == 0.0
    assert sale["wash_sale_window_open"] is False


def test_wash_sale_partial_repurchase_blocks_proportionally(db):
    _eur_portfolio(db)
    c = _company(db, "WS3")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)
    _tx(db, c, date(2026, 1, 20), "buy", 60, 8)  # only 60 of 100 repurchased
    _tx(db, c, date(2026, 6, 1), "buy", 1, 8)    # closes the data window
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS3")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is True
    assert sale["blocked_loss_native"] == 120.0   # 60 shares x 2/share
    assert sale["gain_native"] == -80.0           # remaining loss computable
    assert sale["wash_sale_window_open"] is False


def test_wash_sale_never_blocks_gains(db):
    _eur_portfolio(db)
    c = _company(db, "WS4")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 8)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 10)  # gain +200
    _tx(db, c, date(2026, 1, 20), "buy", 100, 10)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS4")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["gain_native"] == 200.0
    assert sale["blocked_loss_native"] == 0.0


def test_wash_sale_backward_window_blocks_loss(db):
    """A buy in the two months BEFORE the loss sale also blocks it; the
    deferred loss lands on that still-held lot."""
    _eur_portfolio(db)
    c = _company(db, "WS5")
    _tx(db, c, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, c, date(2026, 1, 8), "buy", 100, 9)
    _tx(db, c, date(2026, 1, 10), "sell", 100, 8)  # FIFO sells the @10 lot
    _tx(db, c, date(2026, 6, 1), "sell", 100, 12)  # sells the @9 lot
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS5")
    first, second = row["sales"]
    assert first["wash_sale_blocked"] is True
    assert first["gain_native"] == 0.0
    assert first["blocked_loss_native"] == 200.0
    assert second["cost_native"] == 1100.0  # 900 + 200 deferred
    assert second["gain_native"] == 100.0


def test_wash_sale_window_boundary_is_inclusive(db):
    _eur_portfolio(db)
    inside = _company(db, "WS6")
    _tx(db, inside, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, inside, date(2026, 1, 10), "sell", 100, 8)
    _tx(db, inside, date(2026, 3, 10), "buy", 100, 8)  # exactly 2 months
    outside = _company(db, "WS7")
    _tx(db, outside, date(2026, 1, 5), "buy", 100, 10)
    _tx(db, outside, date(2026, 1, 10), "sell", 100, 8)
    _tx(db, outside, date(2026, 3, 11), "buy", 100, 8)  # 2 months + 1 day
    report = TaxReportService().compute_report(db, 2026)
    sale_in = next(r for r in report["realized"] if r["ticker"] == "WS6")["sales"][0]
    sale_out = next(r for r in report["realized"] if r["ticker"] == "WS7")["sales"][0]
    assert sale_in["wash_sale_blocked"] is True
    assert sale_in["gain_native"] == 0.0
    assert sale_out["wash_sale_blocked"] is False
    assert sale_out["gain_native"] == -200.0


def test_wash_sale_open_window_flagged_when_data_runs_out(db):
    """A loss sale whose 2-month forward window extends past the latest
    available data stays provisionally computable but must be flagged."""
    _eur_portfolio(db)
    c = _company(db, "WS8")
    _tx(db, c, date(2026, 11, 1), "buy", 100, 10)
    _tx(db, c, date(2026, 12, 20), "sell", 100, 8)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "WS8")
    (sale,) = row["sales"]
    assert sale["wash_sale_blocked"] is False
    assert sale["gain_native"] == -200.0
    assert sale["wash_sale_window_open"] is True
    assert row["wash_sale_window_open"] is True
    assert "WS8" in report["summary"]["wash_sale_window_open"]
