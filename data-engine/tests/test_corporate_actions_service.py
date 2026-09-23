"""CorporateActionService contracts: split math must preserve economic value.

Splits and reverse splits rescale quantities and prices while preserving the
money amounts (position value, realized gains, dividend cash). These tests
pin that invariance, the effective-date boundary, idempotent application and
immutability after apply - the tax FIFO ledger depends on all of them.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, CorporateAction, Position, Transaction
from app.services.corporate_actions_service import CorporateActionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str = "AAA") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _position(db, company, *, qty, cost, price):
    position = Position(
        company_id=company.id,
        quantity=Decimal(str(qty)),
        average_cost=Decimal(str(cost)),
        market_price=Decimal(str(price)),
        currency="USD",
    )
    db.add(position)
    db.commit()
    return position


def _tx(db, company, day, action, qty, price):
    tx = Transaction(
        company_id=company.id, trade_date=day, action=action,
        quantity=Decimal(str(qty)), price=Decimal(str(price)),
        fees=Decimal("0"), currency="USD",
    )
    db.add(tx)
    db.commit()
    return tx


def test_split_preserves_position_economic_value(db):
    company = _company(db)
    position = _position(db, company, qty=10, cost=100, price=150)
    service = CorporateActionService()
    action = service.create_action(
        db, ticker="AAA", action_type="split",
        effective_date=date(2026, 6, 1), ratio=Decimal("4"),
    )
    db.refresh(position)
    # 4:1 split: 40 shares at a quarter of the price - same money.
    assert position.quantity == Decimal("40.000000")
    assert position.average_cost == Decimal("25.000000")
    assert position.market_price == Decimal("37.500000")
    assert position.market_value == position.quantity * position.market_price
    assert position.cost_basis_native == position.quantity * position.average_cost
    assert action.applied is True and action.applied_at is not None


def test_split_rescales_only_pre_effective_transactions(db):
    company = _company(db)
    before = _tx(db, company, date(2026, 1, 10), "buy", 10, 100)
    on_date = _tx(db, company, date(2026, 6, 1), "buy", 5, 40)
    after = _tx(db, company, date(2026, 7, 1), "buy", 2, 38)
    CorporateActionService().create_action(
        db, ticker="AAA", action_type="split",
        effective_date=date(2026, 6, 1), ratio=Decimal("2"),
    )
    db.refresh(before)
    db.refresh(on_date)
    db.refresh(after)
    # Pre-effective trade rescaled, money amount preserved (10x100 == 20x50).
    assert before.quantity == Decimal("20.000000")
    assert before.price == Decimal("50.000000")
    assert before.quantity * before.price == Decimal("1000.000000")
    # Trades on/after the effective date are already post-split: untouched.
    assert on_date.quantity == Decimal("5") and on_date.price == Decimal("40")
    assert after.quantity == Decimal("2") and after.price == Decimal("38")


def test_reverse_split(db):
    company = _company(db)
    position = _position(db, company, qty=100, cost=2, price=3)
    CorporateActionService().create_action(
        db, ticker="AAA", action_type="reverse_split",
        effective_date=date(2026, 6, 1), ratio=Decimal("0.1"),
    )
    db.refresh(position)
    assert position.quantity == Decimal("10.000000")
    assert position.average_cost == Decimal("20.000000")
    assert position.cost_basis_native == Decimal("200.000000")


def test_apply_is_idempotent_and_delete_blocked_after_apply(db):
    company = _company(db)
    _position(db, company, qty=10, cost=100, price=150)
    tx = _tx(db, company, date(2026, 1, 10), "buy", 10, 100)
    service = CorporateActionService()
    action = service.create_action(
        db, ticker="AAA", action_type="split",
        effective_date=date(2026, 6, 1), ratio=Decimal("2"),
    )
    service.apply_action(db, action.id)
    db.refresh(tx)
    # Second apply is a no-op: quantity stays 20, not 40.
    assert tx.quantity == Decimal("20.000000")
    with pytest.raises(ValueError, match="immutable"):
        service.delete_action(db, action.id)


def test_unapplied_action_can_be_deleted(db):
    _company(db)
    service = CorporateActionService()
    action = service.create_action(
        db, ticker="AAA", action_type="split",
        effective_date=date(2026, 6, 1), ratio=Decimal("2"), apply_now=False,
    )
    assert action.applied is False
    assert service.delete_action(db, action.id) is True
    assert db.scalar(select(CorporateAction).where(CorporateAction.id == action.id)) is None


def test_invalid_ratio_and_unknown_ticker_rejected(db):
    _company(db)
    service = CorporateActionService()
    with pytest.raises(ValueError, match="positive"):
        service.create_action(
            db, ticker="AAA", action_type="split",
            effective_date=date(2026, 6, 1), ratio=Decimal("0"),
        )
    with pytest.raises(ValueError, match="does not exist"):
        service.create_action(
            db, ticker="NOPE", action_type="split",
            effective_date=date(2026, 6, 1), ratio=Decimal("2"),
        )
