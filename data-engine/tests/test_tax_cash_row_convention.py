"""The cash-row convention is ONE convention, everywhere.

A cash movement (dividend, withholding, interest, fee, cash_misc) stores the
AMOUNT in ``price`` with ``quantity`` 0 or 1. The tax report used to read
``price or quantity`` - truthiness, not ``is not None`` - while every other
consumer multiplied ``quantity * price``. A manual
``{"action": "dividend", "quantity": 100, "price": "0.25"}`` (= 25) was
declared as 0,25 on the fiscal return while XIRR saw 25,00, a silent 100x
error; a legitimate 0,00 dividend fell through to ``quantity`` and was
declared as 1. Both services now share one helper, creation rejects the
ambiguous shape with a 400, and a historical ambiguous row is flagged instead
of being declared in silence.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes import portfolio as portfolio_route
from app.models.entities import Base, Company, Portfolio, Position, Transaction
from app.services import portfolio_intelligence_service as intelligence
from app.services.portfolio_intelligence_service import PortfolioIntelligenceService
from app.services.tax_report_service import (
    TaxReportService,
    cash_amount,
    is_cash_action,
)

YEAR = 2026


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
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _tx(db: Session, company: Company, day: date, action: str, qty, price, currency="EUR") -> Transaction:
    row = Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal("0"), currency=currency, raw_payload={},
    )
    db.add(row)
    db.commit()
    return row


def test_intelligence_uses_the_tax_report_cash_helper(db: Session):
    """One helper, imported by both: the fiscal report and the attribution
    cannot drift apart on the same row again."""
    assert intelligence.cash_amount is cash_amount
    assert intelligence.is_cash_action is is_cash_action


def test_tax_report_and_attribution_report_the_same_cash_amount(db: Session):
    _eur_portfolio(db)
    company = _company(db, "CASH")
    # quantity=0 with the amount in price: the shape the ledger documents and
    # the IBKR importer writes. The old attribution multiplied it by quantity
    # and reported a 25 dividend as 0.
    _tx(db, company, date(2026, 4, 1), "dividend", 0, "25.00")
    _tx(db, company, date(2026, 4, 1), "fee", 1, "1.50")
    position = Position(
        company_id=company.id, quantity=Decimal("10"),
        average_cost=Decimal("10"), cost_basis_native=Decimal("100"),
        market_value=Decimal("200"), market_price=Decimal("20"),
        currency="EUR", base_currency="EUR", as_of=date(2026, 5, 1),
    )
    db.add(position)
    db.commit()

    report = TaxReportService().compute_report(db, YEAR)
    declared = next(d for d in report["dividends"] if d["ticker"] == "CASH")["dividends_native"]
    misc = next(m for m in report["misc"] if m["type"] == "fee")["amount_native"]

    attribution = PortfolioIntelligenceService()._attribution(
        db, [(position, company)], {company.id: 1.0}, {}, date(2026, 1, 1)
    )
    components = attribution["positions"][0]["components"]
    # The attribution expresses dividends as a fraction of cost basis; back out
    # the money it actually used and compare it with the declared figure.
    from_attribution = components["dividends"] * float(position.cost_basis_native)

    assert declared == 25.0
    assert misc == 1.5
    assert from_attribution == pytest.approx(declared)


def test_zero_dividend_reports_zero_not_quantity(db: Session):
    """``price = 0.00`` is a dividend of zero. The old truthiness read fell
    through to ``quantity`` and declared 1.00."""
    _eur_portfolio(db)
    company = _company(db, "ZERO")
    _tx(db, company, date(2026, 4, 1), "dividend", 1, "0.00")

    report = TaxReportService().compute_report(db, YEAR)
    row = next(d for d in report["dividends"] if d["ticker"] == "ZERO")
    assert row["dividends_native"] == 0.0
    assert row["payments"][0]["amount_native"] == 0.0
    assert report["summary"]["total_dividends_base"] == 0.0


def test_zero_quantity_cash_row_is_not_a_zero_amount(db: Session):
    """The mirror case: ``quantity = 0`` is legitimate for cash and must not
    make the amount disappear."""
    _eur_portfolio(db)
    company = _company(db, "Q0")
    _tx(db, company, date(2026, 4, 1), "dividend", 0, "42.00")

    report = TaxReportService().compute_report(db, YEAR)
    row = next(d for d in report["dividends"] if d["ticker"] == "Q0")
    assert row["dividends_native"] == 42.0


def test_ambiguous_cash_row_is_rejected_at_creation(db: Session):
    _eur_portfolio(db)
    payload = portfolio_route.PortfolioTransactionInput(
        ticker="AMB", action="dividend", quantity=Decimal("100"),
        price=Decimal("0.25"), trade_date=date(2026, 4, 1),
    )
    with pytest.raises(HTTPException) as excinfo:
        portfolio_route.create_transaction(payload, db)
    assert excinfo.value.status_code == 400
    assert db.scalar(select(Transaction)) is None

    # The canonical shape is accepted: amount in price, quantity 0 or 1.
    for quantity in (Decimal("0"), Decimal("1")):
        portfolio_route.create_transaction(
            portfolio_route.PortfolioTransactionInput(
                ticker="AMB", action="dividend", quantity=quantity,
                price=Decimal("25"), trade_date=date(2026, 4, 1),
            ),
            db,
        )


def test_ambiguous_cash_row_is_flagged_not_mis_scaled(db: Session):
    """A row already in the ledger is declared with the canonical `price`
    amount, and the ambiguity is surfaced for a human instead of being hidden."""
    _eur_portfolio(db)
    company = _company(db, "AMB")
    _tx(db, company, date(2026, 4, 1), "dividend", 100, "0.25")

    report = TaxReportService().compute_report(db, YEAR)
    row = next(d for d in report["dividends"] if d["ticker"] == "AMB")
    assert row["dividends_native"] == 0.25  # not 25.0, not 100 * 0.25
    flagged = report["summary"]["inconsistent_cash_rows"]
    assert [item["ticker"] for item in flagged] == ["AMB"]
    assert flagged[0]["quantity"] == 100.0
    assert flagged[0]["action"] == "dividend"
