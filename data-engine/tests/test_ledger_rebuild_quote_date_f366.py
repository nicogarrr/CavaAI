"""F366: un rebuild que conserva la cotización guardada no mueve su fecha."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base
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


def test_rebuild_keeps_quote_date_when_quote_is_kept(db):
    service = PortfolioLedgerService()
    _buy(service, db)
    company = service.ensure_company(db, "AAPL")
    position = service.rebuild_position(db, company.id)
    position.market_price = Decimal("120")
    position.as_of = date(2026, 9, 30)
    db.flush()

    _buy(service, db, trade_date=date(2026, 2, 1))
    rebuilt = service.rebuild_position(db, company.id)

    assert rebuilt.market_price == Decimal("120")
    assert rebuilt.as_of == date(2026, 9, 30)


def test_rebuild_without_stored_quote_uses_ledger_date(db):
    service = PortfolioLedgerService()
    _buy(service, db)
    company = service.ensure_company(db, "AAPL")
    position = service.rebuild_position(db, company.id)
    assert position.as_of == date(2026, 1, 10)
