"""Portfolio performance, risk, exposure and return attribution."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CashBalance, Company, FinancialFact, MarketPrice, Position, Transaction
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_snapshot_service import PortfolioSnapshotService


EXCHANGE_COUNTRY = {
    "NASDAQ": "United States",
    "NYSE": "United States",
    "AMEX": "United States",
    "LSE": "United Kingdom",
    "XETRA": "Germany",
    "BME": "Spain",
    "TSX": "Canada",
    "TSE": "Japan",
}


class PortfolioIntelligenceService:
    def build(self, db: Session, *, years: int = 5) -> dict[str, Any]:
        years = max(1, min(years, 20))
        cutoff = date.today() - timedelta(days=365 * years)
        rows = list(
            db.execute(
                select(Position, Company).join(
                    Company, Position.company_id == Company.id
                )
            ).all()
        )
        total_value = sum(
            float(position.market_value_base or 0) for position, _ in rows
        )
        weights = {
            company.id: (
                float(position.market_value_base or 0) / total_value
                if total_value > 0
                else 0
            )
            for position, company in rows
        }
        price_series = {
            company.id: list(
                db.scalars(
                    select(MarketPrice)
                    .where(
                        MarketPrice.company_id == company.id,
                        MarketPrice.date >= cutoff,
                    )
                    .order_by(MarketPrice.date)
                ).all()
            )
            for _, company in rows
        }
        returns = {
            company_id: self._returns(series)
            for company_id, series in price_series.items()
        }
        indicative_returns = self._portfolio_returns(returns, weights)
        snapshots = PortfolioSnapshotService().history(db, start=cutoff)
        snapshot_returns = {
            snapshot.snapshot_date: float(snapshot.daily_return)
            for snapshot in snapshots
            if snapshot.daily_return is not None
        }
        snapshot_exact = self._snapshot_history_is_exact(snapshots)
        portfolio_returns = snapshot_returns if snapshot_exact else indicative_returns
        twr = self._compound(list(portfolio_returns.values()))
        annualized_return = (
            (1 + twr) ** (252 / len(portfolio_returns)) - 1
            if portfolio_returns and twr > -1
            else None
        )
        volatility = (
            pstdev(portfolio_returns.values()) * math.sqrt(252)
            if len(portfolio_returns) >= 2
            else None
        )
        downside = [value for value in portfolio_returns.values() if value < 0]
        downside_volatility = (
            pstdev(downside) * math.sqrt(252) if len(downside) >= 2 else None
        )
        sharpe = (
            annualized_return / volatility
            if annualized_return is not None and volatility not in {None, 0}
            else None
        )
        sortino = (
            annualized_return / downside_volatility
            if annualized_return is not None and downside_volatility not in {None, 0}
            else None
        )
        drawdown = self._drawdown(portfolio_returns)
        xirr, xirr_trace = self._xirr(db, rows)
        correlations = self._correlations(returns, rows)
        beta, beta_trace = self._beta(db, portfolio_returns, cutoff)
        exposures = self._exposures(rows, total_value)
        attribution = self._attribution(db, rows, weights, price_series)
        complete_price_series = sum(len(series) >= 2 for series in price_series.values())
        return {
            "as_of": date.today(),
            "base_currency": PortfolioFXService().base_currency(db),
            "horizon_years": years,
            "performance": {
                "twr": twr if portfolio_returns else None,
                "xirr": xirr,
                "annualized_return": annualized_return,
                "trace": xirr_trace,
                "twr_method": (
                    "daily_portfolio_snapshots"
                    if snapshot_exact
                    else "static_current_weight_estimate"
                ),
                "twr_is_exact": snapshot_exact,
            },
            "risk": {
                "max_drawdown": drawdown["max_drawdown"],
                "drawdown_series": drawdown["series"],
                "volatility": volatility,
                "sharpe": sharpe,
                "sortino": sortino,
                "beta": beta,
                "beta_trace": beta_trace,
                "correlations": correlations,
            },
            "concentration": {
                "top_1": max(weights.values(), default=0),
                "top_5": sum(sorted(weights.values(), reverse=True)[:5]),
                "herfindahl": sum(weight**2 for weight in weights.values()),
                "weights": {
                    company.ticker: weights[company.id] for _, company in rows
                },
            },
            "exposures": exposures,
            "attribution": attribution,
            "coverage": {
                "positions": len(rows),
                "positions_with_price_history": complete_price_series,
                "price_history_percent": (
                    round(100 * complete_price_series / len(rows), 1) if rows else 100
                ),
                "portfolio_snapshots": len(snapshots),
                "snapshot_returns": len(snapshot_returns),
                "snapshot_pricing_complete": sum(
                    snapshot.pricing_coverage == Decimal("1") for snapshot in snapshots
                ),
                "limitations": (
                    []
                    if snapshot_exact
                    else [
                        "TWR uses static current weights until complete daily position and cash snapshots exist.",
                    ]
                )
                + [
                    "Attribution is an evidence-aware decomposition, not transaction-lot Brinson attribution."
                ],
            },
        }

    @staticmethod
    def _snapshot_history_is_exact(snapshots: list[Any]) -> bool:
        if len(snapshots) < 2:
            return False
        for previous, current in zip(snapshots, snapshots[1:]):
            if current.daily_return is None or current.pricing_coverage != Decimal("1"):
                return False
            if (current.snapshot_date - previous.snapshot_date).days > 3:
                return False
            if (current.metadata_ or {}).get("ambiguous_external_flows"):
                return False
        return snapshots[0].pricing_coverage == Decimal("1")

    @staticmethod
    def _returns(series: list[MarketPrice]) -> dict[date, float]:
        result = {}
        for previous, current in zip(series, series[1:]):
            if previous.adj_close and previous.adj_close > 0:
                result[current.date] = float(current.adj_close / previous.adj_close - 1)
        return result

    @staticmethod
    def _portfolio_returns(
        returns: dict[int, dict[date, float]], weights: dict[int, float]
    ) -> dict[date, float]:
        by_date: dict[date, list[tuple[float, float]]] = defaultdict(list)
        for company_id, series in returns.items():
            for day, value in series.items():
                by_date[day].append((weights.get(company_id, 0), value))
        result = {}
        for day, values in sorted(by_date.items()):
            active_weight = sum(weight for weight, _ in values)
            if active_weight > 0:
                result[day] = sum(weight * value for weight, value in values) / active_weight
        return result

    @staticmethod
    def _compound(returns: list[float]) -> float:
        value = 1.0
        for item in returns:
            value *= 1 + item
        return value - 1

    def _drawdown(self, returns: dict[date, float]) -> dict[str, Any]:
        cumulative = 1.0
        peak = 1.0
        minimum = 0.0
        series = []
        for day, value in returns.items():
            cumulative *= 1 + value
            peak = max(peak, cumulative)
            drawdown = cumulative / peak - 1
            minimum = min(minimum, drawdown)
            series.append({"date": day, "drawdown": drawdown})
        return {"max_drawdown": minimum if returns else None, "series": series}

    def _xirr(
        self, db: Session, positions: list[tuple[Position, Company]]
    ) -> tuple[float | None, dict[str, Any]]:
        fx = PortfolioFXService()
        base = fx.base_currency(db)
        cashflows: list[tuple[date, float]] = []
        for transaction in db.scalars(select(Transaction).order_by(Transaction.trade_date)).all():
            rate = fx.rate(
                db,
                quote_currency=transaction.currency,
                base_currency=base,
                as_of=transaction.trade_date,
            )
            if rate is None:
                continue
            amount = float(
                (transaction.quantity * transaction.price + transaction.fees) * rate
            )
            sign = -1 if transaction.action == "buy" else 1
            if transaction.action in {"dividend", "interest"}:
                sign = 1
            cashflows.append((transaction.trade_date, sign * amount))
        ending_value = sum(float(position.market_value_base or 0) for position, _ in positions)
        for cash in db.scalars(select(CashBalance)).all():
            rate = fx.rate(
                db,
                quote_currency=cash.currency,
                base_currency=base,
                as_of=date.today(),
            )
            if rate is not None:
                ending_value += float(cash.balance * rate)
        if ending_value:
            cashflows.append((date.today(), ending_value))
        if len(cashflows) < 2 or not any(value < 0 for _, value in cashflows):
            return None, {"status": "insufficient_cashflows", "cashflows": len(cashflows)}
        origin = min(day for day, _ in cashflows)

        def npv(rate: float) -> float:
            return sum(
                value / ((1 + rate) ** ((day - origin).days / 365.0))
                for day, value in cashflows
            )

        low, high = -0.9999, 10.0
        if npv(low) * npv(high) > 0:
            return None, {"status": "no_xirr_root", "cashflows": len(cashflows)}
        for _ in range(200):
            middle = (low + high) / 2
            if abs(npv(middle)) < 1e-8:
                break
            if npv(low) * npv(middle) <= 0:
                high = middle
            else:
                low = middle
        return middle, {
            "status": "calculated",
            "method": "bisection_xirr",
            "cashflows": len(cashflows),
        }

    @staticmethod
    def _correlations(
        returns: dict[int, dict[date, float]], rows: list[tuple[Position, Company]]
    ) -> dict[str, dict[str, float | None]]:
        result: dict[str, dict[str, float | None]] = {}
        for _, left_company in rows:
            result[left_company.ticker] = {}
            for _, right_company in rows:
                left = returns.get(left_company.id, {})
                right = returns.get(right_company.id, {})
                dates = sorted(left.keys() & right.keys())
                if left_company.id == right_company.id and dates:
                    correlation = 1.0
                elif len(dates) < 3:
                    correlation = None
                else:
                    xs, ys = [left[day] for day in dates], [right[day] for day in dates]
                    x_mean, y_mean = mean(xs), mean(ys)
                    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
                    denominator = math.sqrt(
                        sum((x - x_mean) ** 2 for x in xs)
                        * sum((y - y_mean) ** 2 for y in ys)
                    )
                    correlation = numerator / denominator if denominator else None
                result[left_company.ticker][right_company.ticker] = correlation
        return result

    @staticmethod
    def _beta(
        db: Session, portfolio_returns: dict[date, float], cutoff: date
    ) -> tuple[float | None, dict[str, Any]]:
        benchmark = db.scalar(select(Company).where(Company.ticker == "SPY"))
        if benchmark is None:
            return None, {"status": "missing_benchmark", "benchmark": "SPY"}
        prices = list(
            db.scalars(
                select(MarketPrice)
                .where(MarketPrice.company_id == benchmark.id, MarketPrice.date >= cutoff)
                .order_by(MarketPrice.date)
            ).all()
        )
        benchmark_returns = PortfolioIntelligenceService._returns(prices)
        dates = sorted(portfolio_returns.keys() & benchmark_returns.keys())
        if len(dates) < 20:
            return None, {"status": "insufficient_overlap", "observations": len(dates)}
        portfolio = [portfolio_returns[day] for day in dates]
        market = [benchmark_returns[day] for day in dates]
        market_mean = mean(market)
        variance = sum((value - market_mean) ** 2 for value in market)
        covariance = sum(
            (left - mean(portfolio)) * (right - market_mean)
            for left, right in zip(portfolio, market)
        )
        return (
            covariance / variance if variance else None,
            {"status": "calculated", "benchmark": "SPY", "observations": len(dates)},
        )

    @staticmethod
    def _exposures(
        rows: list[tuple[Position, Company]], total_value: float
    ) -> dict[str, dict[str, float]]:
        exposures: dict[str, dict[str, float]] = {
            "sectors": defaultdict(float),
            "countries": defaultdict(float),
            "currencies": defaultdict(float),
            "factors": defaultdict(float),
        }
        for position, company in rows:
            weight = float(position.market_value_base or 0) / total_value if total_value else 0
            exposures["sectors"][company.sector] += weight
            exposures["countries"][EXCHANGE_COUNTRY.get(company.exchange.upper(), "Unknown")] += weight
            exposures["currencies"][position.currency] += weight
            for factor in company.factor_tags:
                exposures["factors"][factor] += weight
        return {key: dict(value) for key, value in exposures.items()}

    def _attribution(
        self,
        db: Session,
        rows: list[tuple[Position, Company]],
        weights: dict[int, float],
        price_series: dict[int, list[MarketPrice]],
    ) -> dict[str, Any]:
        positions = []
        totals = defaultdict(float)
        for position, company in rows:
            prices = price_series.get(company.id, [])
            total_return = (
                float(prices[-1].adj_close / prices[0].adj_close - 1)
                if len(prices) >= 2 and prices[0].adj_close
                else None
            )
            facts = list(
                db.scalars(
                    select(FinancialFact)
                    .where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.metric.in_(["eps", "shares_diluted"]),
                    )
                    .order_by(FinancialFact.fiscal_year)
                ).all()
            )
            by_metric = defaultdict(list)
            for fact in facts:
                by_metric[fact.metric].append(fact)
            fundamental_growth = self._series_change(by_metric["eps"])
            share_change = self._series_change(by_metric["shares_diluted"])
            dilution = max(share_change or 0, 0)
            buybacks = max(-(share_change or 0), 0)
            dividends = sum(
                float(transaction.quantity * transaction.price)
                for transaction in db.scalars(
                    select(Transaction).where(
                        Transaction.company_id == company.id,
                        Transaction.action == "dividend",
                    )
                ).all()
            )
            dividend_return = (
                dividends / float(position.cost_basis_native)
                if position.cost_basis_native and position.cost_basis_native > 0
                else 0
            )
            fx_component = (
                float(position.fx_rate) - 1 if position.fx_rate is not None else 0
            )
            multiple = (
                total_return
                - (fundamental_growth or 0)
                - dividend_return
                - buybacks
                + dilution
                - fx_component
                if total_return is not None
                else None
            )
            components = {
                "fundamental_growth": fundamental_growth,
                "multiple": multiple,
                "dividends": dividend_return,
                "buybacks": buybacks,
                "dilution": -dilution,
                "fx": fx_component,
                "sizing": (total_return or 0) * weights.get(company.id, 0),
            }
            for key, value in components.items():
                totals[key] += value or 0
            positions.append(
                {
                    "ticker": company.ticker,
                    "weight": weights.get(company.id, 0),
                    "total_return": total_return,
                    "components": components,
                }
            )
        return {"portfolio_components": dict(totals), "positions": positions}

    @staticmethod
    def _series_change(series: list[FinancialFact]) -> float | None:
        annual = [row for row in series if row.fiscal_year is not None]
        if len(annual) < 2 or not annual[0].value:
            return None
        return float(annual[-1].value / annual[0].value - 1)
