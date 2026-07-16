import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, MarketPrice, Position, ResearchAlert, Tenant
from app.services.alert_rule_service import AlertRuleService
from app.services.connectors.ecb import ECBRates
from app.services.market_refresh_service import MarketRefreshService, PriceObservation
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_ledger_service import PortfolioLedgerService


class FixedPrices:
    async def fetch(self, companies, *, as_of):
        return (
            {
                company.ticker: PriceObservation(
                    ticker=company.ticker,
                    price=Decimal("120"),
                    price_date=as_of,
                    source="test-price",
                )
                for company in companies
            },
            [],
        )


class FixedFX:
    async def fetch(self, *, base_currency, quote_currencies):
        assert base_currency == "EUR"
        assert quote_currencies == {"USD"}
        return ECBRates(rate_date=date.today(), rates={"USD": Decimal("0.8")})


def _company(ticker: str) -> Company:
    return Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="TEST",
        currency="USD",
        sector="Test",
        industry="Test",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )


def test_market_refresh_enforces_order_and_alerts_on_fresh_price_only():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="market-test", name="Market test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = _company("FRESH")
        watchlist_company = _company("WATCH")
        db.add_all([company, watchlist_company])
        db.flush()
        PortfolioFXService().set_base_currency(db, "EUR")
        PortfolioLedgerService().create_transaction(
            db,
            ticker=company.ticker,
            action="buy",
            quantity=Decimal("10"),
            price=Decimal("90"),
            trade_date=date.today(),
            currency="USD",
        )
        AlertRuleService().create(
            db,
            company,
            rule_type="price_above",
            operator=">",
            value=100,
        )

        result = asyncio.run(MarketRefreshService(FixedPrices(), FixedFX()).refresh(db))

        assert result["order"] == [
            "update_prices",
            "update_fx",
            "revalue_positions",
            "update_risk",
            "evaluate_alerts",
        ]
        assert result["alert_results"][0]["status"] == "triggered"
        assert result["alert_results"][0]["observation"]["status"] == "fresh"
        position = db.scalar(select(Position))
        assert position is not None
        assert position.market_price == Decimal("120")
        assert position.fx_rate == Decimal("0.8")
        assert position.market_value_base == Decimal("960")
        assert (
            db.scalar(select(MarketPrice).where(MarketPrice.company_id == watchlist_company.id)) is not None
        )
        assert db.scalar(select(ResearchAlert)) is not None


def test_price_alert_explicitly_skips_a_stale_observation():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="stale-test", name="Stale test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = _company("STALE")
        db.add(company)
        db.flush()
        db.add(
            MarketPrice(
                company_id=company.id,
                date=date.today() - timedelta(days=10),
                close=Decimal("120"),
                adj_close=Decimal("120"),
                source="old",
            )
        )
        db.commit()
        rule = AlertRuleService().create(
            db,
            company,
            rule_type="price_above",
            operator=">",
            value=100,
        )

        result = AlertRuleService().evaluate(db, rule)

        assert result["status"] == "skipped_stale_observation"
        assert result["matched"] is False
        assert result["observation"]["status"] == "stale"
        assert result["observation"]["age_days"] == 10
        assert db.scalar(select(ResearchAlert)) is None
