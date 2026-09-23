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


# Exchange -> listing-market country. Best-effort fallback only: the owning
# fact is issuer domicile, and positions without a known exchange are grouped
# under "Unknown" rather than guessed.
EXCHANGE_COUNTRY = {
    "NASDAQ": "United States",
    "NYSE": "United States",
    "AMEX": "United States",
    "NYSEARCA": "United States",
    "LSE": "United Kingdom",
    "XETRA": "Germany",
    "FWB": "Germany",
    "BME": "Spain",
    "EPA": "France",
    "EURONEXT": "Netherlands",
    "BIT": "Italy",
    "SIX": "Switzerland",
    "STO": "Sweden",
    "TSX": "Canada",
    "TSXV": "Canada",
    "TSE": "Japan",
    "HKEX": "Hong Kong",
    "ASX": "Australia",
    "B3": "Brazil",
    "NSE": "India",
    "KRX": "South Korea",
}


class PortfolioIntelligenceService:
    def build(self, db: Session, *, years: int = 5) -> dict[str, Any]:
        years = max(1, min(years, 20))
        cutoff = date.today() - timedelta(days=365 * years)
        fx = PortfolioFXService()
        base_currency = fx.base_currency(db)
        rows = list(
            db.execute(
                select(Position, Company).join(
                    Company, Position.company_id == Company.id
                )
            ).all()
        )
        # Honest valuation: a position without a base-currency value is excluded
        # from totals/weights and reported, never silently counted as zero.
        base_values: dict[int, float] = {}
        missing_fx: list[dict[str, Any]] = []
        for position, company in rows:
            value_base = position.market_value_base
            if value_base is None and position.currency == base_currency:
                value_base = position.market_value_native or position.market_value
            if value_base is None:
                missing_fx.append(
                    {
                        "kind": "position",
                        "ticker": company.ticker,
                        "quote_currency": position.currency,
                        "base_currency": base_currency,
                        "as_of": position.as_of.isoformat() if position.as_of else None,
                    }
                )
                continue
            base_values[position.id] = float(value_base)
        total_value = sum(base_values.values())
        weights = {
            company.id: (
                base_values[position.id] / total_value if total_value > 0 else 0
            )
            for position, company in rows
            if position.id in base_values
        }
        price_series: dict[int, list[MarketPrice]] = {company.id: [] for _, company in rows}
        if rows:
            # Lote: 1 query para todas las series (anti N+1 por posición).
            all_prices = list(
                db.scalars(
                    select(MarketPrice)
                    .where(
                        MarketPrice.company_id.in_([company.id for _, company in rows]),
                        MarketPrice.date >= cutoff,
                    )
                    .order_by(MarketPrice.company_id, MarketPrice.date)
                ).all()
            )
            for price in all_prices:
                price_series.setdefault(price.company_id, []).append(price)
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
        var_95, cvar_95 = self._historical_var(portfolio_returns)
        calmar = (
            annualized_return / abs(drawdown["max_drawdown"])
            if annualized_return is not None
            and drawdown["max_drawdown"] not in {None, 0}
            else None
        )
        xirr, xirr_trace = self._xirr(db, rows)
        correlations = self._correlations(returns, rows)
        beta, beta_trace = self._beta(db, portfolio_returns, cutoff)
        benchmark = self._benchmark_comparison(db, portfolio_returns, cutoff)
        exposures = self._exposures(rows, total_value, base_values)
        attribution = self._attribution(db, rows, weights, price_series)
        ledger_contribution = self._ledger_contribution(db, rows, cutoff)
        complete_price_series = sum(len(series) >= 2 for series in price_series.values())
        return {
            "as_of": date.today(),
            "base_currency": base_currency,
            "missing_fx": missing_fx,
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
                "var_95": var_95,
                "cvar_95": cvar_95,
                "calmar": calmar,
                "beta": beta,
                "beta_trace": beta_trace,
                "correlations": correlations,
            },
            "concentration": {
                "top_1": max(weights.values(), default=0),
                "top_5": sum(sorted(weights.values(), reverse=True)[:5]),
                "herfindahl": sum(weight**2 for weight in weights.values()),
                "weights": {
                    company.ticker: weights[company.id]
                    for _, company in rows
                    if company.id in weights
                },
            },
            "exposures": exposures,
            "attribution": attribution,
            "ledger_contribution": ledger_contribution,
            "benchmark": benchmark,
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
                ]
                + (
                    [
                        f"{len(missing_fx)} position(s) excluded from totals, weights and exposures: no base-currency value (missing FX)."
                    ]
                    if missing_fx
                    else []
                ),
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

    @staticmethod
    def _historical_var(
        returns: dict[date, float], confidence: float = 0.95
    ) -> tuple[float | None, float | None]:
        """Historical-simulation VaR/CVaR on the portfolio daily return series.

        VaR is the return at the (1 - confidence) quantile of observed daily
        returns; CVaR (expected shortfall) is the mean of returns at or below
        that quantile. Both are negative numbers for losses. Requires enough
        observations to be meaningful; otherwise (None, None).
        """
        values = sorted(returns.values())
        if len(values) < 20:
            return None, None
        index = max(0, min(len(values) - 1, int(len(values) * (1 - confidence))))
        var = values[index]
        tail = values[: index + 1]
        cvar = mean(tail) if tail else None
        return var, cvar

    def _xirr(
        self, db: Session, positions: list[tuple[Position, Company]]
    ) -> tuple[float | None, dict[str, Any]]:
        fx = PortfolioFXService()
        base = fx.base_currency(db)
        cashflows: list[tuple[date, float]] = []
        all_transactions = list(db.scalars(select(Transaction).order_by(Transaction.trade_date)).all())
        # Lote FX: 1 query para todos los flujos (anti N+1 por transacción).
        flow_table = fx.fx_table(
            db,
            currencies={transaction.currency for transaction in all_transactions},
            base_currency=base,
            as_of_max=max((t.trade_date for t in all_transactions), default=None) or date.today(),
        ) if all_transactions else {}
        for transaction in all_transactions:
            rate = PortfolioFXService.rate_from_table(
                flow_table,
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
        cash_rows = list(db.scalars(select(CashBalance)).all())
        # Lote FX: 1 query para todas las cajas (anti N+1).
        ending_rates = fx.rates_for(
            db,
            quote_currencies={cash.currency for cash in cash_rows},
            base_currency=base,
            as_of=date.today(),
        )
        for cash in cash_rows:
            rate = ending_rates.get(cash.currency.upper())
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

    def _ledger_contribution(
        self, db: Session, rows: list[tuple[Position, Company]], cutoff: date
    ) -> dict[str, Any]:
        """Per-position P&L contribution over the horizon from the full ledger.

        For each held company: contribution = end value - start value
        - net invested + income, where start value reconstructs the quantity
        held at the horizon cutoff from every prior transaction (the ledger
        is split-adjusted through corporate actions) priced at the last
        close before the cutoff, and net invested sums buys minus sells
        inside the horizon. All flows convert to base currency with
        point-in-time FX; rows without a pre-cutoff price or FX rate get a
        null contribution with an explicit reason instead of an estimate.
        """
        fx = PortfolioFXService()
        base = fx.base_currency(db)
        company_ids = [company.id for _, company in rows]
        empty = {
            "positions": [],
            "total_pnl": None,
            "coverage": {"positions": len(rows), "with_contribution": 0, "reasons": {}},
            "methodology": "ledger_reconstruction_v1",
        }
        if not company_ids:
            return empty

        transactions = list(
            db.scalars(
                select(Transaction)
                .where(Transaction.company_id.in_(company_ids))
                .order_by(Transaction.trade_date)
            ).all()
        )
        by_company: dict[int, list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            if transaction.company_id is not None:
                by_company[transaction.company_id].append(transaction)

        flow_table = fx.fx_table(
            db,
            currencies={t.currency for t in transactions} | {p.currency for p, _ in rows},
            base_currency=base,
            as_of_max=date.today(),
        )

        # Last close strictly before the cutoff per company (one query).
        prior_prices: dict[int, MarketPrice] = {}
        for price in db.scalars(
            select(MarketPrice)
            .where(MarketPrice.company_id.in_(company_ids), MarketPrice.date < cutoff)
            .order_by(MarketPrice.company_id, MarketPrice.date.desc())
        ).all():
            prior_prices.setdefault(price.company_id, price)

        positions_out = []
        reasons: dict[str, int] = defaultdict(int)
        total_pnl = 0.0
        with_contribution = 0
        for position, company in rows:
            ledger = by_company.get(company.id, [])
            qty_at_cutoff = 0.0
            buys = 0.0
            sells = 0.0
            income = 0.0
            fx_missing = False
            for transaction in ledger:
                rate = PortfolioFXService.rate_from_table(
                    flow_table,
                    quote_currency=transaction.currency,
                    base_currency=base,
                    as_of=transaction.trade_date,
                )
                if rate is None:
                    fx_missing = True
                    continue
                amount = float(transaction.quantity * transaction.price) * float(rate)
                fees = float(transaction.fees or 0) * float(rate)
                if transaction.trade_date < cutoff:
                    if transaction.action == "buy":
                        qty_at_cutoff += float(transaction.quantity)
                    elif transaction.action == "sell":
                        qty_at_cutoff -= float(transaction.quantity)
                else:
                    if transaction.action == "buy":
                        buys += amount + fees
                    elif transaction.action == "sell":
                        sells += amount - fees
                    elif transaction.action in {"dividend", "interest"}:
                        income += amount
            start_price_row = prior_prices.get(company.id)
            start_rate = (
                PortfolioFXService.rate_from_table(
                    flow_table,
                    quote_currency=position.currency,
                    base_currency=base,
                    as_of=start_price_row.date,
                )
                if start_price_row is not None
                else None
            )
            end_value = float(position.market_value_base or 0)
            reason = None
            contribution = None
            if fx_missing:
                reason = "missing_fx"
            elif qty_at_cutoff > 0 and (start_price_row is None or not start_price_row.adj_close):
                reason = "missing_start_price"
            elif qty_at_cutoff > 0 and start_rate is None:
                reason = "missing_start_fx"
            if reason is None:
                start_value = (
                    qty_at_cutoff * float(start_price_row.adj_close) * float(start_rate)
                    if qty_at_cutoff > 0 and start_price_row is not None and start_rate is not None
                    else 0.0
                )
                contribution = end_value - start_value - buys + sells + income
                total_pnl += contribution
                with_contribution += 1
            else:
                reasons[reason] += 1
            positions_out.append(
                {
                    "ticker": company.ticker,
                    "contribution_pnl": contribution,
                    "end_value": end_value,
                    "start_value": (
                        qty_at_cutoff * float(start_price_row.adj_close) * float(start_rate)
                        if qty_at_cutoff > 0 and start_price_row is not None and start_rate is not None
                        else 0.0
                    ),
                    "net_invested": buys - sells,
                    "income": income,
                    "reason": reason,
                }
            )
        for entry in positions_out:
            entry["contribution_share"] = (
                entry["contribution_pnl"] / total_pnl
                if entry["contribution_pnl"] is not None and total_pnl != 0
                else None
            )
        return {
            "positions": positions_out,
            "total_pnl": total_pnl if with_contribution else None,
            "coverage": {
                "positions": len(rows),
                "with_contribution": with_contribution,
                "reasons": dict(reasons),
            },
            "methodology": "ledger_reconstruction_v1",
            "base_currency": base,
        }

    def _benchmark_comparison(
        self, db: Session, portfolio_returns: dict[date, float], cutoff: date
    ) -> dict[str, Any]:
        """Portfolio vs SPY over the horizon: returns, alpha, tracking error.

        Honest states: missing_benchmark (SPY not ingested) and
        insufficient_overlap (<20 shared trading days) surface as status
        with null metrics instead of fabricated numbers.
        """
        base: dict[str, Any] = {
            "symbol": "SPY",
            "benchmark_twr": None,
            "benchmark_annualized": None,
            "portfolio_annualized": None,
            "alpha_annualized": None,
            "tracking_error": None,
            "information_ratio": None,
            "observations": 0,
        }
        benchmark = db.scalar(select(Company).where(Company.ticker == "SPY"))
        if benchmark is None:
            return {**base, "status": "missing_benchmark"}
        prices = list(
            db.scalars(
                select(MarketPrice)
                .where(MarketPrice.company_id == benchmark.id, MarketPrice.date >= cutoff)
                .order_by(MarketPrice.date)
            ).all()
        )
        benchmark_returns = self._returns(prices)
        dates = sorted(portfolio_returns.keys() & benchmark_returns.keys())
        if len(dates) < 20:
            return {**base, "status": "insufficient_overlap", "observations": len(dates)}
        port = [portfolio_returns[day] for day in dates]
        bench = [benchmark_returns[day] for day in dates]
        bench_twr = self._compound(bench)
        bench_annualized = (
            (1 + bench_twr) ** (252 / len(bench)) - 1 if bench_twr > -1 else None
        )
        port_twr = self._compound(port)
        port_annualized = (
            (1 + port_twr) ** (252 / len(port)) - 1 if port_twr > -1 else None
        )
        active = [p - b for p, b in zip(port, bench)]
        tracking_error = pstdev(active) * math.sqrt(252) if len(active) >= 2 else None
        alpha = (
            port_annualized - bench_annualized
            if port_annualized is not None and bench_annualized is not None
            else None
        )
        information_ratio = (
            alpha / tracking_error
            # A near-zero tracking error would turn rounding noise into an
            # absurd ratio; treat it as undefined instead.
            if alpha is not None and tracking_error is not None and tracking_error > 1e-6
            else None
        )
        return {
            **base,
            "status": "calculated",
            "benchmark_twr": bench_twr,
            "benchmark_annualized": bench_annualized,
            "portfolio_annualized": port_annualized,
            "alpha_annualized": alpha,
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
            "observations": len(dates),
        }

    @staticmethod
    def _exposures(
        rows: list[tuple[Position, Company]],
        total_value: float,
        base_values: dict[int, float] | None = None,
    ) -> dict[str, dict[str, float]]:
        exposures: dict[str, dict[str, float]] = {
            "sectors": defaultdict(float),
            "countries": defaultdict(float),
            "currencies": defaultdict(float),
            "factors": defaultdict(float),
        }
        for position, company in rows:
            if base_values is None:
                value = float(position.market_value_base or 0)
            else:
                value = base_values.get(position.id)
                if value is None:
                    # No honest base-currency value: reported in missing_fx,
                    # never silently counted as zero exposure.
                    continue
            weight = value / total_value if total_value else 0
            exposures["sectors"][company.sector] += weight
            country = company.domicile_country or EXCHANGE_COUNTRY.get(
                company.exchange.upper(), "Unknown"
            )
            exposures["countries"][country] += weight
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
        company_ids = [company.id for _, company in rows]
        # Lote: 1 query de facts + 1 de dividendos para todas las posiciones
        # (anti N+1 por compañía en attribution).
        all_facts: dict[int, dict[str, list[FinancialFact]]] = defaultdict(lambda: defaultdict(list))
        if company_ids:
            for fact in db.scalars(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id.in_(company_ids),
                    FinancialFact.metric.in_(["eps", "shares_diluted"]),
                )
                .order_by(FinancialFact.company_id, FinancialFact.fiscal_year)
            ).all():
                all_facts[fact.company_id][fact.metric].append(fact)
        all_dividends: dict[int, float] = defaultdict(float)
        if company_ids:
            for dividend in db.scalars(
                select(Transaction).where(
                    Transaction.company_id.in_(company_ids),
                    Transaction.action == "dividend",
                )
            ).all():
                if dividend.company_id is not None:
                    all_dividends[dividend.company_id] += float(
                        dividend.quantity * dividend.price
                    )
        for position, company in rows:
            prices = price_series.get(company.id, [])
            total_return = (
                float(prices[-1].adj_close / prices[0].adj_close - 1)
                if len(prices) >= 2 and prices[0].adj_close
                else None
            )
            by_metric = all_facts.get(company.id, {})
            fundamental_growth = self._series_change(by_metric.get("eps", []))
            share_change = self._series_change(by_metric.get("shares_diluted", []))
            dilution = max(share_change or 0, 0)
            buybacks = max(-(share_change or 0), 0)
            dividends = all_dividends.get(company.id, 0.0)
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
