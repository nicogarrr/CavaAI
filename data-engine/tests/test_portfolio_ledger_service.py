"""PortfolioLedgerService.rebuild_position contract tests.

The ledger is the canonical record; positions are derived. Average-cost
accounting must be exact, invalid ledgers must fail loudly, and base
currency fields must stay None - never guessed - when FX history is
incomplete.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Position
from app.services.portfolio_ledger_service import PortfolioLedgerService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _buy(service, db, **overrides):
    args = {
        "ticker": "AAPL", "action": "buy", "quantity": Decimal("10"),
        "price": Decimal("100"), "trade_date": date(2026, 1, 10), "currency": "EUR",
    }
    args.update(overrides)
    return service.create_transaction(db, **args)


def test_average_cost_and_realized_pnl_from_ledger(db):
    service = PortfolioLedgerService()
    _buy(service, db)                                                     # 10 @ 100
    _buy(service, db, quantity=Decimal("10"), price=Decimal("120"),
         trade_date=date(2026, 2, 10))                                    # 10 @ 120
    _buy(service, db, action="sell", quantity=Decimal("5"),
         price=Decimal("150"), trade_date=date(2026, 3, 10))
    company = service.ensure_company(db, "AAPL")

    position = service.rebuild_position(db, company.id)
    assert position is not None
    assert position.quantity == Decimal("15")
    # Average cost after two buys: (1000+1200)/20 = 110; sell 5 @ 150 -> +200 realized.
    assert position.average_cost == Decimal("110")
    assert position.realized_pnl == Decimal("200")
    assert position.cost_basis_native == Decimal("1650")
    # A stored market price wins over stale trade prices (live feed preserved);
    # the last trade price is only a fallback when no price was ever stored.
    assert position.market_price == Decimal("100")
    assert position.currency == "EUR"
    assert position.source == "postgres_ledger"
    # Same-currency ledger in EUR base: base fields fully populated.
    assert position.cost_basis_base == Decimal("1650")
    assert position.unrealized_pnl_base is not None


def test_oversell_fails_loudly_at_write_time(db):
    service = PortfolioLedgerService()
    _buy(service, db)
    # create_transaction rebuilds the position eagerly: invalid ledgers are
    # rejected when the transaction is written, not later.
    with pytest.raises(ValueError, match="Cannot sell"):
        _buy(service, db, action="sell", quantity=Decimal("11"),
             trade_date=date(2026, 2, 10))


def test_mixed_currency_ledger_rejected_at_write_time(db):
    service = PortfolioLedgerService()
    _buy(service, db)
    with pytest.raises(ValueError, match="cannot mix transaction currencies"):
        _buy(service, db, currency="USD", trade_date=date(2026, 2, 10))


def test_full_sell_removes_position(db):
    service = PortfolioLedgerService()
    _buy(service, db)
    _buy(service, db, action="sell", quantity=Decimal("10"),
         price=Decimal("150"), trade_date=date(2026, 2, 10))
    company = service.ensure_company(db, "AAPL")
    assert service.rebuild_position(db, company.id) is None
    assert db.scalar(select(Position).where(Position.company_id == company.id)) is None


def test_missing_fx_history_leaves_base_fields_none(db):
    service = PortfolioLedgerService()
    # USD ledger with no stored USD->EUR rates at all.
    _buy(service, db, currency="USD")
    company = service.ensure_company(db, "AAPL")
    position = service.rebuild_position(db, company.id)
    assert position.quantity == Decimal("10")
    assert position.average_cost == Decimal("100")  # native accounting unaffected
    assert position.market_value_base is None
    assert position.cost_basis_base is None
    assert position.unrealized_pnl_base is None
    assert position.realized_pnl_base is None


def test_rebuild_position_uses_last_transaction_date_by_default(db):
    service = PortfolioLedgerService()
    _buy(service, db, trade_date=date(2026, 1, 10))
    company = service.ensure_company(db, "AAPL")

    position = service.rebuild_position(db, company.id)

    assert position is not None
    assert position.as_of == date(2026, 1, 10)
