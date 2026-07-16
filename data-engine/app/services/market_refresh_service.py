"""Ordered market refresh: prices -> FX -> positions -> risk -> alerts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, MarketPrice, Position, SavedScreen
from app.services.alert_rule_service import AlertRuleService
from app.services.connectors.ecb import ECBClient, ECBRates
from app.services.connectors.finnhub import FinnhubClient
from app.services.connectors.fmp import FMPClient
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_ledger_service import PortfolioLedgerService
from app.services.risk_service import RiskService
from app.services.screener_service import ScreenerService


@dataclass(frozen=True)
class PriceObservation:
    ticker: str
    price: Decimal
    price_date: date
    source: str


class PriceProvider(Protocol):
    async def fetch(
        self, companies: list[Company], *, as_of: date
    ) -> tuple[dict[str, PriceObservation], list[dict]]: ...


class FXProvider(Protocol):
    async def fetch(self, *, base_currency: str, quote_currencies: set[str]) -> ECBRates: ...


class PublicPriceProvider:
    """FMP first, Finnhub fallback, with per-ticker failure isolation."""

    def __init__(self) -> None:
        self.fmp = FMPClient()
        self.finnhub = FinnhubClient()

    async def fetch(
        self, companies: list[Company], *, as_of: date
    ) -> tuple[dict[str, PriceObservation], list[dict]]:
        rows = await asyncio.gather(*(self._one(company, as_of) for company in companies))
        observations: dict[str, PriceObservation] = {}
        errors: list[dict] = []
        for company, observation, error in rows:
            if observation:
                observations[company.ticker] = observation
            if error:
                errors.append(error)
        return observations, errors

    async def _one(
        self, company: Company, as_of: date
    ) -> tuple[Company, PriceObservation | None, dict | None]:
        errors = []
        if self.fmp.configured():
            try:
                payload = await self.fmp.company_profile(company.ticker)
                item = payload[0] if isinstance(payload, list) and payload else None
                value = Decimal(str(item.get("price"))) if isinstance(item, dict) else None
                if value and value > 0:
                    return company, PriceObservation(company.ticker, value, as_of, "FMP"), None
            except Exception as exc:
                errors.append(f"FMP:{type(exc).__name__}")
        if self.finnhub.configured():
            try:
                payload = await self.finnhub.quote(company.ticker)
                value = Decimal(str(payload.get("c") or 0))
                timestamp = int(payload.get("t") or 0)
                observed_date = datetime.fromtimestamp(timestamp, tz=UTC).date() if timestamp > 0 else as_of
                if value > 0:
                    return company, PriceObservation(company.ticker, value, observed_date, "Finnhub"), None
            except Exception as exc:
                errors.append(f"Finnhub:{type(exc).__name__}")
        reason = ",".join(errors) if errors else "no_price_provider_configured"
        return company, None, {"ticker": company.ticker, "reason": reason}


class ECBFXProvider:
    async def fetch(self, *, base_currency: str, quote_currencies: set[str]) -> ECBRates:
        return await ECBClient().conversion_rates(
            base_currency=base_currency,
            quote_currencies=quote_currencies,
        )


class MarketRefreshService:
    def __init__(
        self,
        price_provider: PriceProvider | None = None,
        fx_provider: FXProvider | None = None,
    ) -> None:
        self.price_provider = price_provider or PublicPriceProvider()
        self.fx_provider = fx_provider or ECBFXProvider()
        self.settings = get_settings()

    async def refresh(self, db: Session, *, as_of: date | None = None) -> dict:
        if db.info.get("tenant_id") is None:
            raise ValueError("Tenant context is required for market refresh")
        as_of = as_of or date.today()
        started = datetime.now(UTC)
        rows = db.execute(
            select(Position, Company)
            .join(Company, Position.company_id == Company.id)
            .order_by(Company.ticker)
        ).all()
        # Prices feed the screener and company alerts as well as the portfolio,
        # so refresh the complete tenant company universe. FX and revaluation
        # remain position-specific in the following stages.
        companies = list(db.scalars(select(Company).order_by(Company.ticker)).all())
        stages: list[dict] = []

        observations, price_errors = await self.price_provider.fetch(companies, as_of=as_of)
        for company in companies:
            observation = observations.get(company.ticker)
            if observation is None:
                continue
            market = db.scalar(
                select(MarketPrice).where(
                    MarketPrice.company_id == company.id,
                    MarketPrice.date == observation.price_date,
                )
            )
            if market is None:
                market = MarketPrice(
                    company_id=company.id,
                    date=observation.price_date,
                )
                db.add(market)
            market.open = observation.price
            market.high = observation.price
            market.low = observation.price
            market.close = observation.price
            market.adj_close = observation.price
            market.source = observation.source
        db.commit()
        stages.append(
            {
                "step": 1,
                "name": "update_prices",
                "status": "ok" if not price_errors else "partial",
                "updated": len(observations),
                "errors": price_errors,
            }
        )

        fx = PortfolioFXService()
        base_currency = fx.base_currency(db)
        quote_currencies = {position.currency.upper() for position, _ in rows}
        fx_errors: list[dict] = []
        fx_updated = 0
        try:
            snapshot = await self.fx_provider.fetch(
                base_currency=base_currency,
                quote_currencies=quote_currencies,
            )
            for currency in quote_currencies:
                rate = snapshot.rates.get(currency)
                if rate is None:
                    fx_errors.append({"currency": currency, "reason": "rate_not_available"})
                    continue
                fx.upsert_rate(
                    db,
                    base_currency=base_currency,
                    quote_currency=currency,
                    rate=rate,
                    rate_date=snapshot.rate_date,
                    source="ECB",
                )
                fx_updated += 1
            db.commit()
        except Exception as exc:
            db.rollback()
            fx_errors.append({"provider": "ECB", "reason": f"{type(exc).__name__}:{exc}"})
        stages.append(
            {
                "step": 2,
                "name": "update_fx",
                "status": "ok" if not fx_errors else "partial",
                "updated": fx_updated,
                "errors": fx_errors,
            }
        )

        ledger = PortfolioLedgerService()
        revalued = 0
        stale_prices: list[dict] = []
        for position, company in rows:
            latest = db.scalar(
                select(MarketPrice)
                .where(MarketPrice.company_id == company.id)
                .order_by(desc(MarketPrice.date))
                .limit(1)
            )
            if latest is None:
                stale_prices.append({"ticker": company.ticker, "status": "missing_market_price"})
                continue
            age_days = (as_of - latest.date).days
            if age_days > self.settings.market_price_max_age_days:
                stale_prices.append(
                    {
                        "ticker": company.ticker,
                        "status": "stale_market_price",
                        "price_date": latest.date.isoformat(),
                        "age_days": age_days,
                    }
                )
            ledger.update_market_price(
                db,
                company_id=company.id,
                price=latest.close,
                as_of=latest.date,
            )
            revalued += 1
        db.commit()
        from app.services.portfolio_snapshot_service import PortfolioSnapshotService

        snapshot = PortfolioSnapshotService().capture(
            db,
            as_of=as_of,
            source="market_refresh",
        )
        db.commit()
        stages.append(
            {
                "step": 3,
                "name": "revalue_positions",
                "status": "ok" if not stale_prices else "stale_data",
                "updated": revalued,
                "stale_prices": stale_prices,
                "portfolio_snapshot_id": snapshot.id,
                "snapshot_pricing_coverage": float(snapshot.pricing_coverage),
            }
        )

        risk = RiskService().dashboard(db)
        risk["market_data_status"] = "stale" if stale_prices else "fresh"
        risk["stale_prices"] = stale_prices
        stages.append(
            {
                "step": 4,
                "name": "update_risk",
                "status": risk["status"],
                "market_data_status": risk["market_data_status"],
            }
        )

        alert_results = AlertRuleService().evaluate_all(db)
        screen_results = []
        for screen in db.scalars(
            select(SavedScreen).where(SavedScreen.active.is_(True)).order_by(SavedScreen.id)
        ).all():
            result = ScreenerService().run_saved(db, screen)
            screen_results.append(
                {
                    "saved_screen_id": screen.id,
                    "matches": result["match_count"],
                    "new_match_company_ids": result["new_match_company_ids"],
                }
            )
        stages.append(
            {
                "step": 5,
                "name": "evaluate_alerts",
                "status": "ok",
                "alert_rules": len(alert_results),
                "saved_screens": len(screen_results),
            }
        )
        return {
            "status": ("ok" if not price_errors and not fx_errors and not stale_prices else "partial"),
            "as_of": as_of,
            "started_at": started,
            "completed_at": datetime.now(UTC),
            "order": [stage["name"] for stage in stages],
            "stages": stages,
            "risk": risk,
            "alert_results": alert_results,
            "screen_results": screen_results,
        }
