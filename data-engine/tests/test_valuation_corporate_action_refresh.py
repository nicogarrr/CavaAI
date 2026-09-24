"""Corporate actions: split preserva valor; reverse-split extremo sin ZeroDivision.

El split reescala cantidades y precios preservando el valor económico
(posición y transacciones anteriores a la fecha efectiva). Un reverse-split
extremo (ratio diminuto pero > 0) no debe dividir por cero; ratio 0 se
rechaza en la creación.
Hermético: SQLite en memoria, sin red.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Position, Transaction
from app.services.corporate_actions_service import CorporateActionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str = "SPL") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
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


def test_split_preserves_economic_value(db):
    company = _company(db)
    _position(db, company, qty="100", cost="50", price="60")
    old = _tx(db, company, date(2026, 1, 10), "buy", 100, 50)
    recent = _tx(db, company, date(2026, 6, 10), "buy", 10, 60)
    value_before = Decimal("100") * Decimal("60")

    service = CorporateActionService()
    action = service.create_action(
        db, ticker="SPL", action_type="split",
        effective_date=date(2026, 6, 1), ratio=Decimal("4"),
        description="4:1",
    )
    assert action.applied is True

    db.refresh(old)
    db.refresh(recent)
    position = db.query(Position).filter_by(company_id=company.id).one()
    # Posición: cantidad ×4, costes /4, valor preservado.
    assert position.quantity == Decimal("400")
    assert position.average_cost == Decimal("12.5")
    assert position.quantity * position.market_price == pytest.approx(value_before)
    # Solo las transacciones ANTERIORES a la fecha efectiva se reescalan.
    assert old.quantity == Decimal("400")
    assert old.price == Decimal("12.5")
    assert recent.quantity == Decimal("10")
    assert recent.price == Decimal("60")
    # Re-aplicar es idempotente.
    again = service.apply_action(db, action.id)
    assert again.applied is True
    db.refresh(old)
    assert old.quantity == Decimal("400")


def test_extreme_reverse_split_has_no_zero_division(db):
    company = _company(db, "RSX")
    _position(db, company, qty="1000000", cost="0.02", price="0.025")
    _tx(db, company, date(2026, 1, 10), "buy", 1000000, "0.02")
    value_before = Decimal("1000000") * Decimal("0.025")

    service = CorporateActionService()
    action = service.create_action(
        db, ticker="RSX", action_type="reverse_split",
        effective_date=date(2026, 6, 1), ratio=Decimal("0.000001"),
        description="1:1000000",
    )
    assert action.applied is True
    position = db.query(Position).filter_by(company_id=company.id).one()
    assert position.quantity == Decimal("1")
    assert position.quantity * position.market_price == pytest.approx(value_before)


def test_zero_or_negative_ratio_rejected(db):
    _company(db)
    service = CorporateActionService()
    with pytest.raises(ValueError, match="positive"):
        service.create_action(
            db, ticker="SPL", action_type="split",
            effective_date=date(2026, 6, 1), ratio=Decimal("0"),
        )
