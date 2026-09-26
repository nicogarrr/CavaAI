"""Ordered market refresh: prices -> FX -> positions -> risk -> alerts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
from app.services.propicks_price_service import yahoo_symbol
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
    """FMP first, Finnhub fallback, with per-ticker failure isolation.

    Bounded concurrency (semaphore of 6 in flight) plus a per-ticker
    timeout: un proveedor lento nunca bloquea el refresh completo ni
    agota las conexiones.
    """

    MAX_IN_FLIGHT = 6
    PER_TICKER_TIMEOUT_SECONDS = 20.0

    def __init__(self) -> None:
        self.fmp = FMPClient()
        self.finnhub = FinnhubClient()

    async def fetch(
        self, companies: list[Company], *, as_of: date
    ) -> tuple[dict[str, PriceObservation], list[dict]]:
        semaphore = asyncio.Semaphore(self.MAX_IN_FLIGHT)
        rows = await asyncio.gather(
            *(self._bounded(company, as_of, semaphore) for company in companies)
        )
        observations: dict[str, PriceObservation] = {}
        errors: list[dict] = []
        for company, observation, error in rows:
            if observation:
                observations[company.ticker] = observation
            if error:
                errors.append(error)
        return observations, errors

    async def _bounded(
        self, company: Company, as_of: date, semaphore: asyncio.Semaphore
    ) -> tuple[Company, PriceObservation | None, dict | None]:
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    self._one(company, as_of),
                    timeout=self.PER_TICKER_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                return company, None, {
                    "ticker": company.ticker,
                    "reason": "per_ticker_timeout",
                }

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


YahooIntradayFetcher = Callable[[list[str]], dict[str, "tuple[Decimal, date]"]]


def fetch_intraday_yahoo(symbols: list[str]) -> dict[str, tuple[Decimal, date]]:
    """Ultimo precio intradia (velas de 15 min) via yfinance. Aislado para tests."""
    import yfinance as yf
    from pandas import Timestamp

    if not symbols:
        return {}
    frame = yf.download(
        " ".join(symbols),
        period="1d",
        interval="15m",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,
    )
    if frame is None or frame.empty:
        return {}
    latest: dict[str, tuple[Decimal, date]] = {}
    for symbol in symbols:
        try:
            try:
                closes = frame[(symbol, "Close")]
            except KeyError:
                closes = frame["Close"]
            closes = closes.dropna()
            if closes.empty:
                continue
            value = Decimal(str(round(float(closes.iloc[-1]), 4)))
            day = Timestamp(closes.index[-1]).date()
            if value > 0:
                latest[symbol] = (value, day)
        except (KeyError, IndexError):
            continue
    return latest


class YahooIntradayPriceProvider:
    """Precios intradia (retardo ~15 min) via Yahoo Finance: gratis, sin key.

    Una sola descarga por lote (yfinance agrupa los tickers), asi el coste
    no crece con el numero de posiciones. Pensado para el refresco de 15
    minutos de la cartera durante la sesion US (F17).
    """

    def __init__(self, fetcher: YahooIntradayFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_intraday_yahoo

    async def fetch(
        self, companies: list[Company], *, as_of: date
    ) -> tuple[dict[str, PriceObservation], list[dict]]:
        yahoo_by_ticker = {company.ticker: yahoo_symbol(company) for company in companies}
        ticker_by_yahoo = {symbol: ticker for ticker, symbol in yahoo_by_ticker.items()}
        try:
            latest = await asyncio.to_thread(self.fetcher, sorted(ticker_by_yahoo))
        except Exception as exc:
            return {}, [{"provider": "yahoo", "reason": f"{type(exc).__name__}:{exc}"}]
        observations: dict[str, PriceObservation] = {}
        for symbol, (value, day) in latest.items():
            ticker = ticker_by_yahoo.get(symbol)
            if ticker is None:
                continue
            observations[ticker] = PriceObservation(
                ticker=ticker, price=value, price_date=day, source="yahoo_finance_intraday"
            )
        errors = [
            {"ticker": company.ticker, "reason": "yahoo_sin_precio_intradia"}
            for company in companies
            if company.ticker not in observations
        ]
        return observations, errors


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

    async def refresh(
        self,
        db: Session,
        *,
        as_of: date | None = None,
        companies: list[Company] | None = None,
    ) -> dict:
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
        if companies is None:
            companies = list(db.scalars(select(Company).order_by(Company.ticker)).all())
        stages: list[dict] = []

        observations, price_errors = await self.price_provider.fetch(companies, as_of=as_of)
        # Batch: one query for every (company, price_date) row we may update.
        observed = [
            (company, observations[company.ticker])
            for company in companies
            if company.ticker in observations
        ]
        existing_prices = {}
        if observed:
            existing_prices = {
                (price.company_id, price.date): price
                for price in db.scalars(
                    select(MarketPrice).where(
                        MarketPrice.company_id.in_([company.id for company, _ in observed]),
                        MarketPrice.date.in_([obs.price_date for _, obs in observed]),
                    )
                ).all()
            }
        for company, observation in observed:
            market = existing_prices.get((company.id, observation.price_date))
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
        # Batch: latest price per position company in one ordered query.
        position_company_ids = list({company.id for _, company in rows})
        latest_prices: dict[int, MarketPrice] = {}
        if position_company_ids:
            for price in db.scalars(
                select(MarketPrice)
                .where(MarketPrice.company_id.in_(position_company_ids))
                .order_by(MarketPrice.company_id, desc(MarketPrice.date))
            ).all():
                latest_prices.setdefault(price.company_id, price)
        # One FX table for every revaluation (point-in-time per row, no N+1).
        refresh_dates = [
            latest_prices[company.id].date
            for _, company in rows
            if company.id in latest_prices
        ]
        fx_table = fx.fx_table(
            db,
            currencies={position.currency for position, _ in rows},
            base_currency=base_currency,
            as_of_max=max(refresh_dates, default=as_of),
        )
        for position, company in rows:
            latest = latest_prices.get(company.id)
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
                position=position,
                fx_rate=PortfolioFXService.rate_from_table(
                    fx_table,
                    quote_currency=position.currency,
                    base_currency=position.base_currency or base_currency,
                    as_of=latest.date,
                ),
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
