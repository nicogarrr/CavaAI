from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Company, Document, FinancialFact, FinancialStatement, MarketPrice
from app.services.connectors.fmp import FMPClient


MetricSpec = tuple[str, str, str]


INCOME_METRICS: list[MetricSpec] = [
    ("revenue", "revenue", "USD"),
    ("gross_profit", "grossProfit", "USD"),
    ("operating_income", "operatingIncome", "USD"),
    ("net_income", "netIncome", "USD"),
    ("ebitda", "ebitda", "USD"),
    ("eps_diluted", "epsdiluted", "USD/share"),
    ("shares_diluted", "weightedAverageShsOutDil", "shares"),
]

BALANCE_METRICS: list[MetricSpec] = [
    ("cash_and_equivalents", "cashAndCashEquivalents", "USD"),
    ("total_debt", "totalDebt", "USD"),
    ("net_debt", "netDebt", "USD"),
    ("total_assets", "totalAssets", "USD"),
    ("total_liabilities", "totalLiabilities", "USD"),
    ("total_equity", "totalStockholdersEquity", "USD"),
]

CASH_FLOW_METRICS: list[MetricSpec] = [
    ("operating_cash_flow", "operatingCashFlow", "USD"),
    ("capital_expenditure", "capitalExpenditure", "USD"),
    ("free_cash_flow", "freeCashFlow", "USD"),
    ("common_stock_repurchased", "commonStockRepurchased", "USD"),
    ("dividends_paid", "dividendsPaid", "USD"),
]

RATIO_METRICS: list[MetricSpec] = [
    ("gross_margin", "grossProfitMargin", "decimal"),
    ("operating_margin", "operatingProfitMargin", "decimal"),
    ("net_margin", "netProfitMargin", "decimal"),
    ("debt_to_equity", "debtEquityRatio", "decimal"),
]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _period(row: dict[str, Any]) -> tuple[str, int | None, str | None]:
    fiscal_year = row.get("calendarYear") or row.get("fiscalYear")
    fiscal_quarter = row.get("period")
    date_value = row.get("date")

    year_int: int | None = None
    if fiscal_year is not None:
        try:
            year_int = int(fiscal_year)
        except (TypeError, ValueError):
            year_int = None

    if date_value and fiscal_quarter:
        return f"{date_value}:{fiscal_quarter}", year_int, str(fiscal_quarter)
    if year_int and fiscal_quarter:
        return f"{year_int}:{fiscal_quarter}", year_int, str(fiscal_quarter)
    if date_value:
        return str(date_value), year_int, None
    return "unknown", year_int, str(fiscal_quarter) if fiscal_quarter else None


def _rows(payload: list | dict) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


class FinancialIngestionService:
    """Normalize provider data into auditable financial facts."""

    async def refresh_from_fmp(
        self,
        db: Session,
        company: Company,
        client: FMPClient | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        fmp = client or FMPClient()
        ticker = company.ticker.upper()

        income = _rows(await fmp.income_statement(ticker, limit=limit))
        balance = _rows(await fmp.balance_sheet(ticker, limit=limit))
        cash_flow = _rows(await fmp.cash_flow(ticker, limit=limit))
        ratios = _rows(await fmp.ratios(ticker, limit=limit))
        profile = _rows(await fmp.company_profile(ticker))

        document = self._source_document(db, company)
        self._replace_fmp_data(db, company, document)

        statements = 0
        facts = 0
        for statement_type, rows, specs in [
            ("income", income, INCOME_METRICS),
            ("balance_sheet", balance, BALANCE_METRICS),
            ("cash_flow", cash_flow, CASH_FLOW_METRICS),
            ("ratios", ratios, RATIO_METRICS),
        ]:
            for row in rows:
                statements += self._add_statement(
                    db=db,
                    company=company,
                    document=document,
                    statement_type=statement_type,
                    row=row,
                )
                facts += self._add_facts(
                    db=db,
                    company=company,
                    document=document,
                    row=row,
                    specs=specs,
                )

        db.flush()
        facts += self._add_derived_facts(db, company, document)
        self._add_profile_price(db, company, profile)

        document.metadata_ = {
            **(document.metadata_ or {}),
            "provider": "FMP",
            "last_refreshed_at": datetime.now(UTC).isoformat(),
            "income_rows": len(income),
            "balance_rows": len(balance),
            "cash_flow_rows": len(cash_flow),
            "ratio_rows": len(ratios),
        }
        db.commit()

        return {
            "status": "ingested",
            "ticker": ticker,
            "provider": "FMP",
            "source_document_id": document.id,
            "facts_imported": facts,
            "statements_imported": statements,
            "latest_periods": self.latest_periods(db, company),
            "valuation_input_ready": self.valuation_input_ready(db, company),
        }

    def latest_periods(self, db: Session, company: Company) -> dict[str, str | None]:
        periods: dict[str, str | None] = {}
        for metric in ["revenue", "free_cash_flow", "net_debt", "shares_diluted"]:
            fact = self.latest_fact(db, company, metric)
            periods[metric] = fact.period if fact else None
        return periods

    def valuation_input_ready(self, db: Session, company: Company) -> bool:
        return all(
            self.latest_fact(db, company, metric)
            for metric in ["revenue", "free_cash_flow", "shares_diluted"]
        )

    def latest_fact(self, db: Session, company: Company, metric: str) -> FinancialFact | None:
        return db.scalar(
            select(FinancialFact)
            .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
            .order_by(
                FinancialFact.fiscal_year.desc().nullslast(),
                FinancialFact.created_at.desc(),
            )
            .limit(1)
        )

    def _source_document(self, db: Session, company: Company) -> Document:
        title = f"FMP normalized financials - {company.ticker}"
        document = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_type == "FMP",
                Document.title == title,
            )
        )
        if document:
            return document
        document = Document(
            company_id=company.id,
            title=title,
            source_type="FMP",
            source_url=f"https://financialmodelingprep.com/financial-summary/{company.ticker}",
            metadata_={"provider": "FMP", "normalized": True},
        )
        db.add(document)
        db.flush()
        return document

    def _replace_fmp_data(self, db: Session, company: Company, document: Document) -> None:
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "FMP",
            )
        )
        db.execute(
            delete(FinancialStatement).where(
                FinancialStatement.company_id == company.id,
                FinancialStatement.source_id == document.id,
            )
        )
        db.flush()

    def _add_statement(
        self,
        db: Session,
        company: Company,
        document: Document,
        statement_type: str,
        row: dict[str, Any],
    ) -> int:
        period, fiscal_year, fiscal_quarter = _period(row)
        db.add(
            FinancialStatement(
                company_id=company.id,
                statement_type=statement_type,
                period=period,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                source_id=document.id,
                facts=row,
            )
        )
        return 1

    def _add_facts(
        self,
        db: Session,
        company: Company,
        document: Document,
        row: dict[str, Any],
        specs: list[MetricSpec],
    ) -> int:
        period, fiscal_year, fiscal_quarter = _period(row)
        count = 0
        for metric, fmp_key, unit in specs:
            value = _decimal(row.get(fmp_key))
            if value is None:
                continue
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=value,
                    unit=unit,
                    period=period,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    source_id=document.id,
                    source_type="FMP",
                    is_reported=True,
                    confidence=Decimal("0.90"),
                )
            )
            count += 1
        return count

    def _add_derived_facts(self, db: Session, company: Company, document: Document) -> int:
        revenue_facts = list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == "revenue")
                .order_by(FinancialFact.fiscal_year.desc().nullslast())
                .limit(2)
            )
        )
        count = 0
        latest_revenue = revenue_facts[0] if revenue_facts else None
        prior_revenue = revenue_facts[1] if len(revenue_facts) > 1 else None
        latest_fcf = self.latest_fact(db, company, "free_cash_flow")
        operating_cash_flow = self.latest_fact(db, company, "operating_cash_flow")
        capex = self.latest_fact(db, company, "capital_expenditure")
        total_debt = self.latest_fact(db, company, "total_debt")
        cash = self.latest_fact(db, company, "cash_and_equivalents")

        if not latest_fcf and operating_cash_flow and capex:
            count += self._add_derived_fact(
                db,
                company,
                document,
                "free_cash_flow",
                operating_cash_flow.value + capex.value,
                "USD",
                operating_cash_flow.period,
                operating_cash_flow.fiscal_year,
                operating_cash_flow.fiscal_quarter,
            )
            db.flush()
            latest_fcf = self.latest_fact(db, company, "free_cash_flow")

        if latest_revenue and latest_fcf and latest_revenue.value:
            count += self._add_derived_fact(
                db,
                company,
                document,
                "fcf_margin",
                latest_fcf.value / latest_revenue.value,
                "decimal",
                latest_revenue.period,
                latest_revenue.fiscal_year,
                latest_revenue.fiscal_quarter,
            )
        if latest_revenue and prior_revenue and prior_revenue.value:
            count += self._add_derived_fact(
                db,
                company,
                document,
                "revenue_growth",
                latest_revenue.value / prior_revenue.value - Decimal("1"),
                "decimal",
                latest_revenue.period,
                latest_revenue.fiscal_year,
                latest_revenue.fiscal_quarter,
            )
        if total_debt and cash and not self.latest_fact(db, company, "net_debt"):
            count += self._add_derived_fact(
                db,
                company,
                document,
                "net_debt",
                total_debt.value - cash.value,
                "USD",
                total_debt.period,
                total_debt.fiscal_year,
                total_debt.fiscal_quarter,
            )
        return count

    def _add_derived_fact(
        self,
        db: Session,
        company: Company,
        document: Document,
        metric: str,
        value: Decimal,
        unit: str,
        period: str,
        fiscal_year: int | None,
        fiscal_quarter: str | None,
    ) -> int:
        db.add(
            FinancialFact(
                company_id=company.id,
                metric=metric,
                value=value,
                unit=unit,
                period=period,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                source_id=document.id,
                source_type="FMP",
                is_reported=False,
                is_adjusted=True,
                confidence=Decimal("0.85"),
            )
        )
        return 1

    def _add_profile_price(
        self,
        db: Session,
        company: Company,
        profile: list[dict[str, Any]],
    ) -> None:
        if not profile:
            return
        price = _decimal(profile[0].get("price"))
        if price is None or price <= 0:
            return
        today = datetime.now(UTC).date()
        existing = db.scalar(
            select(MarketPrice).where(MarketPrice.company_id == company.id, MarketPrice.date == today)
        )
        if existing:
            existing.close = price
            existing.adj_close = price
            existing.source = "FMP"
            return
        db.add(
            MarketPrice(
                company_id=company.id,
                date=today,
                open=price,
                high=price,
                low=price,
                close=price,
                adj_close=price,
                source="FMP",
            )
        )
