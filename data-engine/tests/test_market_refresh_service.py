"""MarketRefreshService contracts: batched price lookups + staged honesty.

refresh() must not scale its market_prices query count with the number of
companies/positions (stage 1 upserts and stage 3 latest-price lookups are
batched), and every stage reports its honest status instead of hiding gaps.
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.entities import Base, Company, MarketPrice, Portfolio, Position
from app.services.connectors.ecb import ECBRates
from app.services.market_refresh_service import (
    MarketRefreshService,
    PriceObservation,
    _provider_date,
)


@pytest.fixture
def db():
    # Production SessionLocal uses expire_on_commit=False; mirror it so
    # expired-attribute reloads do not appear as phantom per-row queries.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


class _FakePriceProvider:
    async def fetch(self, companies, *, as_of):
        observations = {
            company.ticker: PriceObservation(
                ticker=company.ticker,
                price=Decimal("100"),
                price_date=as_of,
                source="fake",
            )
            for company in companies
        }
        return observations, []


class _FakeFXProvider:
    async def fetch(self, *, base_currency, quote_currencies):
        return ECBRates(
            rate_date=date(2026, 9, 22),
            rates={currency: Decimal("1.1") for currency in quote_currencies},
        )


def _seed(db: Session, n: int) -> None:
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    for i in range(n):
        company = Company(
            ticker=f"T{i:02d}", name=f"T{i:02d}", exchange="NASDAQ", currency="USD",
            sector="S", industry="I", company_type="holding",
            valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
        )
        db.add(company)
        db.flush()
        db.add(Position(
            company_id=company.id, quantity=Decimal("10"), currency="USD",
            market_price=Decimal("90"), market_value=Decimal("900"),
        ))
        # Pre-existing older price row: exercises the stage-1 upsert hit path.
        db.add(MarketPrice(
            company_id=company.id, date=date(2026, 9, 20),
            close=Decimal("95"), adj_close=Decimal("95"), source="seed",
        ))
    db.commit()


def _refresh_and_count(db: Session) -> tuple[dict, int]:
    statements = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        service = MarketRefreshService(
            price_provider=_FakePriceProvider(), fx_provider=_FakeFXProvider()
        )
        result = asyncio.run(service.refresh(db, as_of=date(2026, 9, 22)))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    counts = {}
    for table in ("market_prices", "positions", "fx_rates"):
        counts[table] = len([
            s for s in statements
            if s.lstrip().upper().startswith("SELECT") and table in s
        ])
    return result, counts


def test_refresh_query_count_is_constant_in_company_count(db):
    _seed(db, 3)
    _, count_small = _refresh_and_count(db)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as db2:
        db2.info["tenant_id"] = "tenant-test"
        _seed(db2, 8)
        _, count_large = _refresh_and_count(db2)

    # Stage-1 upsert lookups, stage-3 latest-price/position/FX lookups are
    # batched: no count may grow with the number of companies/positions.
    assert count_small == count_large


def test_refresh_writes_prices_and_reports_stages(db):
    _seed(db, 4)
    result, _ = _refresh_and_count(db)

    assert [stage["name"] for stage in result["stages"]] == [
        "update_prices", "update_fx", "revalue_positions", "update_risk", "evaluate_alerts",
    ]
    assert result["stages"][0]["status"] == "ok"
    assert result["stages"][0]["updated"] == 4
    assert result["stages"][1]["status"] == "ok"
    assert result["stages"][2]["updated"] == 4

    prices = db.scalars(
        select(MarketPrice).where(MarketPrice.date == date(2026, 9, 22))
    ).all()
    assert len(prices) == 4
    assert all(price.close == Decimal("100") for price in prices)
    # Positions revalued from the refreshed close.
    for position in db.scalars(select(Position)).all():
        assert position.market_price == Decimal("100")
        assert position.market_value == Decimal("1000")
        # FX came from the stage-2 upsert (1.1) through the batched table.
        assert position.fx_rate == Decimal("1.1")
        assert position.market_value_base == Decimal("1100")


class TestProviderDate:
    """_provider_date: ISO/timezone honesto, sin slices magicos de strptime."""

    def test_iso_with_negative_offset_uses_utc_date(self):
        # 23:30 a -05:00 ya es el dia siguiente en UTC: la fecha de la quote
        # es la UTC, no la del huso del proveedor.
        assert _provider_date(
            {"date": "2026-09-26T23:30:00-05:00"}, date(2026, 9, 27)
        ) == date(2026, 9, 27)

    def test_iso_with_positive_offset_uses_utc_date(self):
        assert _provider_date(
            {"date": "2026-09-26T00:30:00+02:00"}, date(2026, 9, 26)
        ) == date(2026, 9, 25)

    def test_iso_z_and_fractional_seconds(self):
        assert _provider_date(
            {"datetime": "2026-09-26T15:30:00Z"}, date(2026, 9, 27)
        ) == date(2026, 9, 26)
        assert _provider_date(
            {"datetime": "2026-09-26T15:30:00.123456"}, date(2026, 9, 27)
        ) == date(2026, 9, 26)

    def test_date_only_and_compact(self):
        assert _provider_date({"date": "2026-09-26"}, date(2026, 9, 27)) == date(2026, 9, 26)
        assert _provider_date({"date": "20260926"}, date(2026, 9, 27)) == date(2026, 9, 26)

    def test_epoch_timestamp(self):
        expected = datetime.fromtimestamp(1_758_900_000, tz=UTC).date()
        assert _provider_date({"timestamp": 1_758_900_000}, date(2026, 9, 27)) == expected

    def test_garbage_or_missing_is_none_never_fallback(self):
        assert _provider_date({"date": "not a date"}, date(2026, 9, 26)) is None
        assert _provider_date({"date": ""}, date(2026, 9, 26)) is None
        assert _provider_date({}, date(2026, 9, 26)) is None
