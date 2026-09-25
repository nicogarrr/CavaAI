"""Sourced screener ratios from stored daily closes and financial facts.

Never pair financial statements across fiscal years, never mix currencies,
and never turn missing, seed or unverified inputs into apparent signals.
Ratios are computed from SEC/ESEF facts plus the latest stored daily close;
missing inputs stay null (honest "sin datos"), never fabricated.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact, MarketPrice


_METRICS = {"eps_diluted", "total_equity", "shares_diluted", "net_income"}
_TRUSTED_SOURCES = {"SEC", "ESEF"}
_PRICE_MAX_AGE_DAYS = 7  # weekends/holidays around the latest trading day
_FACT_MAX_AGE_YEARS = 2


def _ratio(value: Decimal | None) -> float | None:
    if value is None or not value.is_finite():
        return None
    number = float(value)
    return round(number, 4) if isfinite(number) else None


def _unit_currency(unit: str | None) -> str:
    """Normalize 'USD', 'iso4217:EUR' and 'iso4217:EUR/xbrli:shares' to 'USD'/'EUR'."""
    text = (unit or "").upper().strip()
    if text.startswith("ISO4217:"):
        text = text[len("ISO4217:"):]
    return text.split("/", 1)[0].strip()


def load_screener_ratios(db: Session, symbols: set[str], *, today: date | None = None) -> dict[str, dict]:
    """Bulk-load pe/pb/roe without N+1 queries. Missing/stale inputs stay null.

    Each ratio uses one complete annual snapshot (same fiscal year, same
    filing family): PE = close / diluted EPS, PB = close / (equity / shares),
    ROE = net income / equity * 100. Currency must match the company's quote
    currency; negative EPS or equity yields a null ratio, not a fake number.
    """
    if not symbols:
        return {}
    today = today or date.today()
    normalized = {symbol.upper() for symbol in symbols}
    companies = list(db.scalars(select(Company).where(Company.ticker.in_(normalized))))
    ids = [row.id for row in companies]
    if not ids:
        return {}
    prices = db.scalars(
        select(MarketPrice)
        .where(MarketPrice.company_id.in_(ids), MarketPrice.date >= today - timedelta(days=_PRICE_MAX_AGE_DAYS))
        .order_by(MarketPrice.date.desc(), MarketPrice.id.desc())
    ).all()
    facts = db.scalars(
        select(FinancialFact)
        .where(
            FinancialFact.company_id.in_(ids),
            FinancialFact.metric.in_(_METRICS),
            FinancialFact.fiscal_year >= today.year - _FACT_MAX_AGE_YEARS,
            FinancialFact.source_type.in_(_TRUSTED_SOURCES),
            FinancialFact.is_reported.is_(True),
            FinancialFact.fiscal_quarter.is_(None),
        )
        .order_by(FinancialFact.fiscal_year.desc(), FinancialFact.created_at.desc(), FinancialFact.id.desc())
    ).all()
    latest_price: dict[int, MarketPrice] = {}
    for row in prices:
        if row.company_id not in latest_price and row.source.lower() not in {"seed", "mock", "test"} and row.close and row.close > 0:
            latest_price[row.company_id] = row
    by_company: dict[int, dict[tuple[int, str], FinancialFact]] = {}
    for fact in facts:
        if fact.period.upper() not in {"FY", "ANNUAL"} or fact.fiscal_year is None:
            continue
        by_company.setdefault(fact.company_id, {}).setdefault((fact.fiscal_year, fact.metric), fact)

    output: dict[str, dict] = {}
    for company in companies:
        price = latest_price.get(company.id)
        metrics: dict = {"pe": None, "pb": None, "roe": None}
        if not price:
            output[company.ticker.upper()] = metrics
            continue
        currency = (company.currency or "").upper()
        facts_for_company = by_company.get(company.id, {})
        years = sorted({year for year, _ in facts_for_company}, reverse=True)
        provenance = {"price": {"source": price.source, "date": price.date.isoformat(), "id": price.id}, "facts": {}}

        def pair(left: str, right: str):
            for year in years:
                a = facts_for_company.get((year, left))
                b = facts_for_company.get((year, right))
                if a and b and a.value is not None and b.value is not None and b.value > 0:
                    return a, b
            return None

        for year in years:
            eps = facts_for_company.get((year, "eps_diluted"))
            if eps and eps.value and eps.value > 0 and _unit_currency(eps.unit) == currency:
                metrics["pe"] = _ratio(price.close / eps.value)
                provenance["facts"]["pe"] = {"id": eps.id, "source": eps.source_type, "year": year}
                break
        equity_shares = pair("total_equity", "shares_diluted")
        if equity_shares:
            equity, shares = equity_shares
            if equity.value > 0 and _unit_currency(equity.unit) == currency and (shares.unit or "").lower() == "shares":
                metrics["pb"] = _ratio(price.close / (equity.value / shares.value))
                provenance["facts"]["pb"] = {"ids": [equity.id, shares.id], "sources": [equity.source_type, shares.source_type], "year": equity.fiscal_year}
        income_equity = pair("net_income", "total_equity")
        if income_equity:
            income, equity = income_equity
            if _unit_currency(income.unit) == currency and _unit_currency(equity.unit) == currency:
                metrics["roe"] = _ratio(income.value / equity.value * 100)
                provenance["facts"]["roe"] = {"ids": [income.id, equity.id], "sources": [income.source_type, equity.source_type], "year": income.fiscal_year}
        if provenance["facts"]:
            metrics["ratioProvenance"] = provenance
        output[company.ticker.upper()] = metrics
    return output
