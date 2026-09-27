from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, MarketPrice, NewsEvent, Portfolio, Position, Tenant
from app.services.portfolio_moves_service import build_digest, latest_digest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def test_tenant_digest_missing_and_news_are_not_causal(db):
    first = Tenant(external_id="tenant-first", name="First", metadata_={}, status="active")
    second = Tenant(external_id="tenant-second", name="Second", metadata_={}, status="active")
    db.add_all((first, second))
    db.flush()
    company = Company(ticker="TEST", name="Test", exchange="NASDAQ", currency="USD",
                      company_type="holding", valuation_model="unassigned")
    db.add(company)
    db.flush()
    portfolio = Portfolio(tenant_id=first.id, name="A")
    db.add(portfolio)
    db.flush()
    db.add(Position(tenant_id=first.id, portfolio_id=portfolio.id, company_id=company.id,
                    quantity=Decimal("2"), average_cost=Decimal("10")))
    db.add_all((MarketPrice(company_id=company.id, date=date(2026, 9, 23), close=Decimal("10"), source="feed"),
                MarketPrice(company_id=company.id, date=date(2026, 9, 24), close=Decimal("11"), source="feed")))
    db.add(NewsEvent(tenant_id=first.id, company_id=company.id, date=datetime(2026, 9, 24, 8, tzinfo=UTC),
                     title="Related article", source="example.com", url="https://example.com/a", metadata_={"connector": "gdelt"}))
    db.add(NewsEvent(tenant_id=second.id, company_id=company.id, date=datetime(2026, 9, 24, 8, tzinfo=UTC),
                     title="Private other tenant", source="example.com", url="https://example.com/b"))
    db.commit()
    db.info["tenant_id"] = first.id
    digest = build_digest(db, date(2026, 9, 24), datetime(2026, 9, 25, tzinfo=UTC))
    assert digest.items[0]["price_change_pct"] == 10
    assert digest.items[0]["catalyst"] == "sin catalizador identificado"
    assert [row["url"] for row in digest.items[0]["related_news"]] == ["https://example.com/a"]
    assert build_digest(db, date(2026, 9, 24), datetime(2026, 9, 25, tzinfo=UTC)).id == digest.id
    db.info["tenant_id"] = second.id
    assert latest_digest(db)["status"] == "sin datos"


def test_missing_close_and_intraday_guard(db):
    db.info["tenant_id"] = 999
    with pytest.raises(ValueError):
        build_digest(db, date(2026, 9, 25), datetime(2026, 9, 25, 12, tzinfo=UTC))
    assert build_digest(db, date(2026, 9, 24), datetime(2026, 9, 25, tzinfo=UTC)).coverage == "sin posiciones"
