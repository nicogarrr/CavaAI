"""F363: recapturar un día antiguo recalcula retorno y TWR de las fotos posteriores."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, PortfolioDailySnapshot, Position
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_snapshot_service import PortfolioSnapshotService

D0 = date(2026, 9, 1)
D1 = D0 + timedelta(days=1)
D2 = D0 + timedelta(days=2)


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        company = Company(
            ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
            sector="Tech", industry="Tech", company_type="holding",
            valuation_model="unassigned", special_sources=[], special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.commit()
        portfolio = PortfolioFXService().ensure_portfolio(db)
        position = Position(
            portfolio_id=portfolio.id, company_id=company.id, quantity=Decimal("10"),
            market_price=Decimal("100"), currency="EUR", as_of=D0,
        )
        db.add(position)
        db.commit()
        yield db, portfolio, position


def _snap(db, day, position, price):
    position.as_of = day
    position.market_price = Decimal(price)
    db.commit()
    return PortfolioSnapshotService().capture(db, as_of=day)


def test_recapturing_middle_day_updates_following_returns(setup):
    db, _, position = setup
    _snap(db, D0, position, "100")      # 1000
    _snap(db, D1, position, "110")      # 1100  (+10%)
    third = _snap(db, D2, position, "121")  # 1210 (+10%)
    assert third.cumulative_twr == pytest.approx(Decimal("0.21"))

    _snap(db, D1, position, "100")      # D1 recapturado a 1000 (0%)
    db.expire_all()
    snaps = {s.snapshot_date: s for s in db.query(PortfolioDailySnapshot).all()}
    assert snaps[D1].daily_return == pytest.approx(Decimal("0"))
    # D2 ahora enlaza con 1000: 1210/1000 - 1 = 21%; el acumulado es 21%, no 21% por casualidad
    assert snaps[D2].daily_return == pytest.approx(Decimal("0.21"))
    assert snaps[D2].cumulative_twr == pytest.approx(Decimal("0.21"))


def test_recapture_that_breaks_the_link_blanks_following_twr(setup):
    db, _, position = setup
    _snap(db, D0, position, "100")
    _snap(db, D1, position, "110")
    _snap(db, D2, position, "121")
    first = db.query(PortfolioDailySnapshot).filter_by(snapshot_date=D1).one()
    first.pricing_coverage = Decimal("0.5")
    db.commit()
    # recapturar D1 con una posición cuyo as_of no coincide (cobertura < 1)
    position.as_of = D0
    position.market_price = Decimal("110")
    db.commit()
    PortfolioSnapshotService().capture(db, as_of=D1)
    db.expire_all()
    snaps = {s.snapshot_date: s for s in db.query(PortfolioDailySnapshot).all()}
    assert snaps[D1].pricing_coverage != Decimal("1")
    assert snaps[D2].daily_return is None
    assert snaps[D2].cumulative_twr is None
