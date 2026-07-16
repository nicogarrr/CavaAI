"""Historical per-share fundamentals and valuation multiples for charting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact, MarketPrice


class HistoricalValuationService:
    METRICS = {
        "eps",
        "free_cash_flow",
        "revenue",
        "shares_diluted",
        "total_debt",
        "cash_and_equivalents",
    }

    def build(
        self, db: Session, company: Company, *, years: int = 10
    ) -> dict[str, Any]:
        minimum_year = date.today().year - max(1, min(years, 20)) + 1
        prices = list(
            db.scalars(
                select(MarketPrice)
                .where(
                    MarketPrice.company_id == company.id,
                    MarketPrice.date >= date(minimum_year, 1, 1),
                )
                .order_by(MarketPrice.date)
            ).all()
        )
        facts = list(
            db.scalars(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.metric.in_(self.METRICS),
                    FinancialFact.fiscal_year >= minimum_year,
                )
                .order_by(
                    FinancialFact.fiscal_year,
                    FinancialFact.metric,
                    desc(FinancialFact.id),
                )
            ).all()
        )
        annual_prices: dict[int, MarketPrice] = {}
        for row in prices:
            annual_prices[row.date.year] = row
        annual_facts: dict[int, dict[str, FinancialFact]] = {}
        for row in facts:
            if row.fiscal_year is None or (row.fiscal_quarter or "").upper().startswith("Q"):
                continue
            annual_facts.setdefault(row.fiscal_year, {}).setdefault(row.metric, row)

        series = []
        for year in sorted(annual_prices.keys() | annual_facts.keys()):
            price_row = annual_prices.get(year)
            year_facts = annual_facts.get(year, {})
            price = price_row.close if price_row else None
            shares = self._value(year_facts, "shares_diluted")
            eps = self._value(year_facts, "eps")
            fcf = self._value(year_facts, "free_cash_flow")
            revenue = self._value(year_facts, "revenue")
            debt = self._value(year_facts, "total_debt") or Decimal("0")
            cash = self._value(year_facts, "cash_and_equivalents") or Decimal("0")
            market_cap = price * shares if price is not None and shares is not None else None
            enterprise_value = (
                market_cap + debt - cash if market_cap is not None else None
            )
            series.append(
                {
                    "year": year,
                    "price": price,
                    "eps": eps,
                    "fcf_per_share": self._divide(fcf, shares),
                    "revenue_per_share": self._divide(revenue, shares),
                    "pe": self._divide(price, eps),
                    "ev_to_fcf": self._divide(enterprise_value, fcf),
                    "ev_to_revenue": self._divide(enterprise_value, revenue),
                    "source_ids": {
                        "market_price": price_row.id if price_row else None,
                        **{key: row.id for key, row in year_facts.items()},
                    },
                }
            )

        multiple_keys = ("pe", "ev_to_fcf", "ev_to_revenue")
        statistics = {
            key: self._statistics(
                [point[key] for point in series if point[key] is not None]
            )
            for key in multiple_keys
        }
        missing = {
            metric: [point["year"] for point in series if point[metric] is None]
            for metric in (
                "price",
                "eps",
                "fcf_per_share",
                "revenue_per_share",
                *multiple_keys,
            )
        }
        return {
            "ticker": company.ticker,
            "currency": company.currency,
            "years_requested": years,
            "series": series,
            "statistics": statistics,
            "coverage": {
                "points": len(series),
                "complete_valuation_points": sum(
                    all(point[key] is not None for key in multiple_keys)
                    for point in series
                ),
                "missing_by_metric": missing,
            },
            "definitions": {
                "price": "Last stored close in each calendar year",
                "fcf_per_share": "Annual free cash flow / diluted shares",
                "revenue_per_share": "Annual revenue / diluted shares",
                "pe": "Price / EPS",
                "ev_to_fcf": "(price * diluted shares + debt - cash) / FCF",
                "ev_to_revenue": "(price * diluted shares + debt - cash) / revenue",
            },
        }

    @staticmethod
    def _value(rows: dict[str, FinancialFact], metric: str) -> Decimal | None:
        row = rows.get(metric)
        return row.value if row else None

    @staticmethod
    def _divide(
        numerator: Decimal | None, denominator: Decimal | None
    ) -> Decimal | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator

    def _statistics(self, values: list[Decimal]) -> dict[str, Decimal | None]:
        ordered = sorted(values)
        if not ordered:
            return {
                "median": None,
                "percentile_10": None,
                "percentile_25": None,
                "percentile_75": None,
                "percentile_90": None,
            }
        return {
            "median": self._percentile(ordered, Decimal("0.5")),
            "percentile_10": self._percentile(ordered, Decimal("0.1")),
            "percentile_25": self._percentile(ordered, Decimal("0.25")),
            "percentile_75": self._percentile(ordered, Decimal("0.75")),
            "percentile_90": self._percentile(ordered, Decimal("0.9")),
        }

    @staticmethod
    def _percentile(values: list[Decimal], quantile: Decimal) -> Decimal:
        if len(values) == 1:
            return values[0]
        position = quantile * Decimal(len(values) - 1)
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight
