from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, Position
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_ledger_service import PortfolioLedgerService


def test_portfolio_uses_historical_cost_fx_and_current_market_fx():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        company = Company(
            ticker="FXCO",
            name="FX Company",
            exchange="NYSE",
            currency="USD",
            sector="Test",
            industry="Test",
            company_type="generic",
            valuation_model="dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()

        fx = PortfolioFXService()
        portfolio = fx.set_base_currency(db, "EUR")
        fx.upsert_rate(
            db,
            base_currency="EUR",
            quote_currency="USD",
            rate=Decimal("0.90"),
            rate_date=date(2026, 1, 2),
            source="test",
        )
        fx.upsert_rate(
            db,
            base_currency="EUR",
            quote_currency="USD",
            rate=Decimal("0.80"),
            rate_date=date(2026, 2, 2),
            source="test",
        )

        ledger = PortfolioLedgerService()
        ledger.create_transaction(
            db,
            ticker=company.ticker,
            action="buy",
            quantity=Decimal("10"),
            price=Decimal("100"),
            trade_date=date(2026, 1, 2),
            currency="USD",
        )
        ledger.update_market_price(
            db,
            company_id=company.id,
            price=Decimal("120"),
            as_of=date(2026, 2, 2),
        )
        db.commit()

        position = db.scalar(select(Position).where(Position.company_id == company.id))
        assert position is not None
        assert position.portfolio_id == portfolio.id
        assert position.currency == "USD"
        assert position.base_currency == "EUR"
        assert position.average_cost == Decimal("100")
        assert position.cost_basis_native == Decimal("1000")
        assert position.cost_basis_base == Decimal("900")
        assert position.market_value_native == Decimal("1200")
        assert position.market_value_base == Decimal("960")
        assert position.unrealized_pnl_base == Decimal("60")
        assert position.fx_rate == Decimal("0.8")


def test_portfolio_does_not_silently_convert_without_an_fx_rate():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(
            Company(
                ticker="NOFX",
                name="No FX",
                exchange="TSE",
                currency="JPY",
                sector="Test",
                industry="Test",
                company_type="generic",
                valuation_model="dcf",
                special_sources=[],
                special_risks=[],
                factor_tags=[],
            )
        )
        db.commit()
        ledger = PortfolioLedgerService()
        ledger.create_transaction(
            db,
            ticker="NOFX",
            action="buy",
            quantity=Decimal("2"),
            price=Decimal("1000"),
            trade_date=date(2026, 1, 2),
            currency="JPY",
        )
        db.commit()
        position = db.scalar(select(Position))
        assert position is not None
        assert position.market_value_native == Decimal("2000")
        assert position.market_value_base is None
        assert position.cost_basis_base is None
