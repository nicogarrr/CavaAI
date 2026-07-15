from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import FXRate, Portfolio


class PortfolioFXService:
    """Tenant-scoped portfolio configuration and point-in-time FX lookup."""

    def portfolio(self, db: Session) -> Portfolio | None:
        return db.scalar(
            select(Portfolio)
            .where(Portfolio.is_default.is_(True))
            .order_by(Portfolio.id)
            .limit(1)
        )

    def base_currency(self, db: Session) -> str:
        portfolio = self.portfolio(db)
        return (portfolio.base_currency if portfolio else "EUR").upper()

    def ensure_portfolio(self, db: Session) -> Portfolio:
        portfolio = self.portfolio(db)
        if portfolio is None:
            portfolio = Portfolio(name="Main", base_currency="EUR", is_default=True)
            db.add(portfolio)
            db.flush()
        return portfolio

    def set_base_currency(self, db: Session, currency: str) -> Portfolio:
        normalized = currency.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Base currency must be a three-letter ISO currency")
        portfolio = self.ensure_portfolio(db)
        portfolio.base_currency = normalized
        db.flush()
        return portfolio

    def rate(
        self,
        db: Session,
        *,
        quote_currency: str,
        base_currency: str,
        as_of: date,
    ) -> Decimal | None:
        quote = quote_currency.upper()
        base = base_currency.upper()
        if quote == base:
            return Decimal("1")
        direct = db.scalar(
            select(FXRate)
            .where(
                FXRate.base_currency == base,
                FXRate.quote_currency == quote,
                FXRate.rate_date <= as_of,
            )
            .order_by(desc(FXRate.rate_date), desc(FXRate.created_at))
            .limit(1)
        )
        if direct:
            return direct.rate
        inverse = db.scalar(
            select(FXRate)
            .where(
                FXRate.base_currency == quote,
                FXRate.quote_currency == base,
                FXRate.rate_date <= as_of,
            )
            .order_by(desc(FXRate.rate_date), desc(FXRate.created_at))
            .limit(1)
        )
        if inverse and inverse.rate:
            return Decimal("1") / inverse.rate
        return None

    def upsert_rate(
        self,
        db: Session,
        *,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        rate_date: date,
        source: str,
    ) -> FXRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        if len(base) != 3 or len(quote) != 3 or not base.isalpha() or not quote.isalpha():
            raise ValueError("FX currencies must use three-letter ISO codes")
        if base == quote and rate != Decimal("1"):
            raise ValueError("Same-currency FX rate must equal 1")
        if rate <= 0:
            raise ValueError("FX rate must be positive")
        row = db.scalar(
            select(FXRate).where(
                FXRate.base_currency == base,
                FXRate.quote_currency == quote,
                FXRate.rate_date == rate_date,
            )
        )
        if row is None:
            row = FXRate(
                base_currency=base,
                quote_currency=quote,
                rate_date=rate_date,
            )
            db.add(row)
        row.rate = rate
        row.source = source.strip()[:80] or "manual"
        db.flush()
        return row
