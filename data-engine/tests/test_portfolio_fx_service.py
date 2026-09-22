"""PortfolioFXService contract tests.

FX conversion touches every portfolio number the user sees: rates must
resolve point-in-time (never from the future), fall back to the inverse
pair, stay None when unknown, and reject invalid quotes at write time.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, FXRate
from app.services.portfolio_fx_service import PortfolioFXService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def test_same_currency_is_one_without_data(db):
    assert PortfolioFXService().rate(
        db, quote_currency="eur", base_currency="EUR", as_of=date(2026, 9, 23)
    ) == Decimal("1")


def test_rate_is_point_in_time_never_from_the_future(db):
    service = PortfolioFXService()
    service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                        rate=Decimal("1.10"), rate_date=date(2026, 9, 1), source="ecb")
    service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                        rate=Decimal("9.99"), rate_date=date(2026, 12, 31), source="ecb")
    db.commit()
    # The December rate exists but is in the future relative to as_of.
    assert service.rate(
        db, quote_currency="USD", base_currency="EUR", as_of=date(2026, 9, 23)
    ) == Decimal("1.10")
    assert service.rate(
        db, quote_currency="USD", base_currency="EUR", as_of=date(2026, 8, 1)
    ) is None  # nothing stored on or before August


def test_inverse_pair_used_when_direct_missing(db):
    service = PortfolioFXService()
    service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                        rate=Decimal("2.00"), rate_date=date(2026, 9, 1), source="ecb")
    db.commit()
    assert service.rate(
        db, quote_currency="EUR", base_currency="USD", as_of=date(2026, 9, 23)
    ) == Decimal("0.5")


def test_rate_from_table_replicates_point_in_time_semantics(db):
    service = PortfolioFXService()
    service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                        rate=Decimal("1.10"), rate_date=date(2026, 9, 1), source="ecb")
    service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                        rate=Decimal("9.99"), rate_date=date(2026, 12, 31), source="ecb")
    db.commit()
    table = service.fx_table(
        db, currencies={"USD"}, base_currency="EUR", as_of_max=date(2026, 9, 23)
    )
    # The December rate never even enters the table (lookahead filtered).
    assert service.rate_from_table(
        table, quote_currency="USD", base_currency="EUR", as_of=date(2026, 9, 23)
    ) == Decimal("1.10")
    assert service.rate_from_table(
        table, quote_currency="USD", base_currency="EUR", as_of=date(2026, 8, 1)
    ) is None
    assert service.rate_from_table(
        table, quote_currency="EUR", base_currency="USD", as_of=date(2026, 9, 23)
    ) == pytest.approx(Decimal("1") / Decimal("1.10"))
    assert service.rate_from_table(
        table, quote_currency="EUR", base_currency="EUR", as_of=date(2026, 9, 23)
    ) == Decimal("1")


def test_upsert_rate_validates_and_updates_in_place(db):
    service = PortfolioFXService()
    with pytest.raises(ValueError, match="three-letter ISO"):
        service.upsert_rate(db, base_currency="EURO", quote_currency="USD",
                            rate=Decimal("1"), rate_date=date(2026, 9, 1), source="x")
    with pytest.raises(ValueError, match="must be positive"):
        service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                            rate=Decimal("0"), rate_date=date(2026, 9, 1), source="x")
    with pytest.raises(ValueError, match="must equal 1"):
        service.upsert_rate(db, base_currency="EUR", quote_currency="EUR",
                            rate=Decimal("1.1"), rate_date=date(2026, 9, 1), source="x")

    first = service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                                rate=Decimal("1.10"), rate_date=date(2026, 9, 1), source="ecb")
    second = service.upsert_rate(db, base_currency="EUR", quote_currency="USD",
                                 rate=Decimal("1.12"), rate_date=date(2026, 9, 1), source="manual")
    assert first.id == second.id
    assert db.query(FXRate).count() == 1
    assert db.get(FXRate, first.id).rate == Decimal("1.12")
    assert db.get(FXRate, first.id).source == "manual"
