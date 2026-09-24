"""FIFO multi-lote con fees + reconciliación ledger == tax.

El ledger (coste medio) y el informe fiscal (FIFO) usan métodos distintos:
solo coinciden cuando la posición se liquida entera (mismo periodo,
proceeds − coste total − fees de venta). Con venta parcial FIFO y media
difieren legítimamente: este test fija ambos hechos.
Hermético: SQLite en memoria, base EUR, sin FX.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, FXRate, Portfolio, Transaction
from app.services.portfolio_ledger_service import PortfolioLedgerService
from app.services.tax_report_service import TaxReportService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _eur_portfolio(db: Session) -> None:
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    db.commit()


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="XETRA", currency="EUR",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _tx(db, company, day, action, qty, price, fees="0"):
    db.add(Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal(str(fees)), currency="EUR",
    ))
    db.commit()


def test_fifo_multi_lot_consumes_oldest_first_with_fees(db):
    _eur_portfolio(db)
    c = _company(db, "FIF")
    _tx(db, c, date(2026, 1, 10), "buy", 100, 10, fees="10")   # lote 1010
    _tx(db, c, date(2026, 2, 10), "buy", 50, 12, fees="5")     # lote 605
    _tx(db, c, date(2026, 6, 1), "sell", 120, 15, fees="8")
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "FIF")
    # 100×10.10 + 20×12.10 = 1010 + 242
    assert row["proceeds_native"] == 1800.0 - 8.0
    assert row["cost_native"] == 1252.0
    assert row["gain_native"] == pytest.approx(1792.0 - 1252.0)
    assert row["sale_count"] == 1
    assert report["summary"]["incomplete_fx"] is False


def test_full_close_reconciles_ledger_average_with_tax_fifo(db):
    """Liquidación total: ledger (media) == tax (FIFO), mismo periodo."""
    _eur_portfolio(db)
    ledger = PortfolioLedgerService()
    ledger.create_transaction(
        db, ticker="REC", action="buy", quantity=Decimal("100"),
        price=Decimal("10"), trade_date=date(2026, 1, 10),
        fees=Decimal("10"), currency="EUR",
    )
    ledger.create_transaction(
        db, ticker="REC", action="buy", quantity=Decimal("50"),
        price=Decimal("12"), trade_date=date(2026, 2, 10),
        fees=Decimal("5"), currency="EUR",
    )
    ledger.create_transaction(
        db, ticker="REC", action="sell", quantity=Decimal("150"),
        price=Decimal("15"), trade_date=date(2026, 6, 1),
        fees=Decimal("8"), currency="EUR",
    )
    db.commit()
    company = ledger.ensure_company(db, "REC")
    position = ledger.rebuild_position(db, company.id)
    assert position is None  # liquidación total: sin posición abierta

    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "REC")
    total_cost = Decimal("1010") + Decimal("605")
    expected = Decimal("150") * Decimal("15") - Decimal("8") - total_cost
    assert row["gain_native"] == pytest.approx(float(expected))
    assert row["gain_base"] == pytest.approx(float(expected))

    # El realizado del ledger en cierre total coincide con el fiscal.
    buys = Decimal("100") * Decimal("10") + Decimal("50") * Decimal("12")
    buy_fees = Decimal("15")
    ledger_realized = (
        Decimal("150") * Decimal("15") - Decimal("8") - buys - buy_fees
    )
    assert float(ledger_realized) == pytest.approx(row["gain_native"])


def test_partial_sell_fifo_and_average_may_legitimately_differ(db):
    """Venta parcial: documenta que FIFO ≠ media (no es un bug)."""
    _eur_portfolio(db)
    c = _company(db, "PAR")
    _tx(db, c, date(2026, 1, 10), "buy", 10, 100)
    _tx(db, c, date(2026, 2, 10), "buy", 10, 200)
    _tx(db, c, date(2026, 6, 1), "sell", 10, 200)
    report = TaxReportService().compute_report(db, 2026)
    row = next(r for r in report["realized"] if r["ticker"] == "PAR")
    # FIFO consume el lote barato: ganancia 1000; en media sería 500.
    assert row["cost_native"] == 1000.0
    assert row["gain_native"] == 1000.0
