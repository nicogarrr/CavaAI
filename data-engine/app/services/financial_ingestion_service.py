from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Company, Document, FinancialFact, FinancialStatement, MarketPrice
from app.services.connectors import fred as fred_connector
from app.services.connectors import sec_edgar as sec_edgar_connector
from app.services.connectors import esef as esef_connector
from app.services.fact_chunk_service import sync_company_fact_chunks
from app.services.connectors.fmp import FMPClient
from app.services.connectors.sec import SECClient


MetricSpec = tuple[str, str, str]


INCOME_METRICS: list[MetricSpec] = [
    ("revenue", "revenue", "USD"),
    ("gross_profit", "grossProfit", "USD"),
    ("operating_income", "operatingIncome", "USD"),
    ("income_before_tax", "incomeBeforeTax", "USD"),
    ("income_tax_expense", "incomeTaxExpense", "USD"),
    ("interest_expense", "interestExpense", "USD"),
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
    ("goodwill", "goodwill", "USD"),
    ("intangible_assets", "intangibleAssets", "USD"),
    ("operating_lease_liabilities", "operatingLeaseLiabilities", "USD"),
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
    ("effective_tax_rate", "effectiveTaxRate", "decimal"),
]

SEC_METRIC_MAP: list[tuple[str, list[str], str]] = [
    ("revenue",           ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],  "USD"),
    ("gross_profit",      ["GrossProfit"],                                                                          "USD"),
    ("operating_income",  ["OperatingIncomeLoss"],                                                                  "USD"),
    ("income_before_tax", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], "USD"),
    ("income_tax_expense", ["IncomeTaxExpenseBenefit"],                                                             "USD"),
    ("interest_expense",   ["InterestExpenseNonOperating", "InterestExpense"],                                      "USD"),
    ("net_income",        ["NetIncomeLoss", "ProfitLoss"],                                                          "USD"),
    ("eps_diluted",       ["EarningsPerShareDiluted"],                                                              "USD/share"),
    ("shares_diluted",    ["WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding"],      "shares"),
    # Fallback aprobado por Nico (25/9, WWW): el tag combinado incluye caja
    # restringida -> deuda neta fresca pero algo optimista. Va el ULTIMO: por
    # periodo gana el `filed` mas reciente, y los periodos donde se uso quedan
    # anotados en document.metadata_["cash_includes_restricted_periods"].
    ("cash_and_equivalents", ["CashAndCashEquivalentsAtCarryingValue",
                              "CashCashEquivalentsAndShortTermInvestments",
                              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], "USD"),
    ("total_debt",        ["LongTermDebt", "LongTermDebtNoncurrent", "DebtLongtermAndShorttermCombinedAmount"],     "USD"),
    ("total_assets",      ["Assets"],                                                                               "USD"),
    ("total_liabilities", ["Liabilities"],                                                                          "USD"),
    ("total_equity",      ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "USD"),
    ("goodwill",          ["Goodwill"],                                                                              "USD"),
    ("intangible_assets", ["FiniteLivedIntangibleAssetsNet", "IndefiniteLivedIntangibleAssetsExcludingGoodwill"],    "USD"),
    ("operating_lease_liabilities", ["OperatingLeaseLiability", "OperatingLeaseLiabilityNoncurrent"],                "USD"),
    ("operating_cash_flow", ["NetCashProvidedByUsedInOperatingActivities"],                                         "USD"),
    ("capital_expenditure", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],          "USD"),
    ("depreciation_amortization", ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                                   "Depreciation", "DepreciationAndAmortization"],                                                                  "USD"),
    ("dividends_paid",    ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],                                "USD"),
]


# IFRS (ESEF) -> metricas internas. Mismo contrato que SEC: los alias se
# FUSIONAN por periodo (gana el primer alias que informa el periodo, NUNCA
# se suman tags). Solo conceptos verificados en los snapshots reales de los
# 6 emisores reviewed (24-25/9). Huecos honestos: total_debt (IFRS reparte
# borrowings current/noncurrent/lease y sumarlos esta prohibido) y
# shares_diluted (ninguno de los 6 reviewed trae WeightedAverageNumberOfShares
# en base scope). EBITDA no es tag IFRS estandar: se deriva como
# operating_income + D&A en _derive_esef_metrics (no aplica a bancos sin
# beneficio operativo, p.ej. SAN).
ESEF_METRIC_MAP: list[tuple[str, list[str], str]] = [
    ("revenue",           ["ifrs-full:Revenue", "ifrs-full:RevenueFromInterest"],                        "iso4217:EUR"),
    ("net_income",        ["ifrs-full:ProfitLoss"],                                                      "iso4217:EUR"),
    ("operating_income",  ["ifrs-full:ProfitLossFromOperatingActivities"],                               "iso4217:EUR"),
    ("gross_profit",      ["ifrs-full:GrossProfit"],                                                     "iso4217:EUR"),
    ("income_before_tax", ["ifrs-full:ProfitLossBeforeTax"],                                             "iso4217:EUR"),
    ("income_tax_expense", ["ifrs-full:IncomeTaxExpenseContinuingOperations"],                           "iso4217:EUR"),
    ("interest_expense",  ["ifrs-full:InterestExpense", "ifrs-full:FinanceCosts"],                       "iso4217:EUR"),
    ("depreciation_amortization", ["ifrs-full:DepreciationAndAmortisationExpense",
                                   "ifrs-full:AdjustmentsForDepreciationAndAmortisationExpense"],        "iso4217:EUR"),
    ("eps_diluted",       ["ifrs-full:DilutedEarningsLossPerShare", "ifrs-full:BasicEarningsLossPerShare"], "iso4217:EUR/xbrli:shares"),
    ("total_assets",      ["ifrs-full:Assets"],                                                          "iso4217:EUR"),
    ("total_liabilities", ["ifrs-full:Liabilities"],                                                     "iso4217:EUR"),
    ("total_equity",      ["ifrs-full:EquityAttributableToOwnersOfParent", "ifrs-full:Equity"],          "iso4217:EUR"),
    ("cash_and_equivalents", ["ifrs-full:CashAndCashEquivalents"],                                       "iso4217:EUR"),
    ("operating_cash_flow", ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],                        "iso4217:EUR"),
    ("capital_expenditure", ["ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                             "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
                             # Concepto combinado estandar IFRS (PP&E + intangibles + otras no
                             # corrientes): lo usan emisores que no desagregan el capex, p.ej. REP.
                             "ifrs-full:PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"],
                                                                                                        "iso4217:EUR"),
    ("dividends_paid",    ["ifrs-full:DividendsPaidClassifiedAsFinancingActivities"],                    "iso4217:EUR"),
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


async def _free_data_snapshot(ticker: str, cik: str) -> dict[str, Any]:
    """Snapshot best-effort de filings EDGAR (10-K/10-Q) + macro FRED.

    Nunca lanza excepciones: cada fuente falla por separado y sin clave FRED
    el macro simplemente queda en None.
    """
    snapshot: dict[str, Any] = {
        "status": "ok",
        "recent_filings": [],
        "macro": None,
    }
    try:
        snapshot["recent_filings"] = await sec_edgar_connector.recent_filings(
            cik, forms=("10-K", "10-Q"), limit=5
        )
    except Exception as exc:
        snapshot["recent_filings"] = []
        snapshot["filings_error"] = str(exc)[:200]
    try:
        snapshot["macro"] = await fred_connector.latest_observation("cpi")
    except Exception as exc:  # pragma: no cover - red defensiva
        snapshot["macro"] = None
        snapshot["macro_error"] = str(exc)[:200]
    return snapshot


class FinancialIngestionService:
    """Normalize provider data into auditable financial facts."""

    async def refresh_from_fmp(
        self,
        db: Session,
        company: Company,
        client: FMPClient | None = None,
        # FMP free tier rejects limit>=6 on /stable statements with 402;
        # 5 periods is the deepest history the free key serves.
        limit: int = 5,
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
        facts += self._add_profile_facts(db, company, document, profile)
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

    async def refresh_from_sec(self, db: Session, company: Company) -> dict[str, Any]:
        sec = SECClient()
        ticker = company.ticker.upper()

        try:
            cik = await sec.cik_for_ticker(ticker)
        except Exception as e:
            raise RuntimeError(f"SEC fetch failed: {e}") from e

        if not cik:
            raise RuntimeError(f"Sin CIK para {ticker}: este emisor no reporta a la SEC; usa la fuente de su mercado local (ESEF para emisores de la UE)")

        try:
            facts_data = await sec.company_facts(cik)
        except Exception as e:
            raise RuntimeError(f"SEC fetch failed: {e}") from e

        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})

        document = self._source_document_sec(db, company, ticker)
        self._replace_sec_data(db, company)

        facts_imported = 0
        cash_restricted_years: set[int] = set()

        for metric, concepts, unit in SEC_METRIC_MAP:
            xbrl_unit_key = "USD/shares" if unit == "USD/share" else unit
            # Los alias se FUSIONAN, no "gana el primero que informe": muchos
            # filers migraron de tag (Revenues -> SalesRevenueNet ->
            # RevenueFromContractWithCustomer...) y el tag antiguo queda
            # congelado en el pasado. Fusion por periodo (`end`) conservando
            # el `filed` mas reciente: mismo periodo bajo dos tags = una sola
            # vez, con su presentacion mas reciente (recast incluido).
            by_end: dict[str, dict[str, Any]] = {}
            for concept in concepts:
                concept_data = us_gaap.get(concept, {})
                entries = concept_data.get("units", {}).get(xbrl_unit_key, [])
                annual = [
                    e for e in entries
                    if e.get("fp") == "FY" and e.get("form") in {"10-K", "20-F"}
                ]
                # OJO: `fy` es el ANIO DEL FILING, no el del periodo. Un 10-K
                # de FY2025 trae revenue de 2025, 2024 y 2023; el ano fiscal
                # correcto es el del `end`. Ante re-presentaciones del mismo
                # periodo manda el `filed` mas reciente.
                for entry in annual:
                    end = str(entry.get("end") or "")
                    if not end:
                        continue
                    current = by_end.get(end)
                    if current is None or str(entry.get("filed", "")) > str(
                        current.get("filed", "")
                    ):
                        by_end[end] = {**entry, "_concept": concept}
            if by_end:
                annual_sorted = sorted(
                    by_end.values(), key=lambda e: str(e["end"]), reverse=True
                )[:10]
                for entry in annual_sorted:
                    val = _decimal(entry.get("val"))
                    if val is None:
                        continue
                    if metric == "capital_expenditure":
                        val = -val
                    if (
                        metric == "cash_and_equivalents"
                        and entry.get("_concept")
                        == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
                    ):
                        cash_restricted_years.add(int(str(entry["end"])[:4]))
                    db.add(
                        FinancialFact(
                            company_id=company.id,
                            metric=metric,
                            value=val,
                            unit=unit,
                            period=f"{entry['end']}:FY",
                            fiscal_year=int(str(entry["end"])[:4]),
                            fiscal_quarter="FY",
                            source_id=document.id,
                            source_type="SEC",
                            is_reported=True,
                            confidence=Decimal("0.95"),
                        )
                    )
                    facts_imported += 1

        db.flush()

        if cash_restricted_years:
            document.metadata_ = {
                **(document.metadata_ or {}),
                # Nota de cobertura: estos ejercicios usan caja + caja
                # restringida (el emisor dejo de reportar caja estricta).
                # La deuda neta derivada es ligeramente optimista en ellos.
                "cash_includes_restricted_periods": sorted(cash_restricted_years),
            }
        facts_imported += self._derive_sec_metrics(db, company, document)

        conflicts: list[str] = []
        sec_facts = list(
            db.scalars(
                select(FinancialFact).where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.source_type == "SEC",
                )
            )
        )
        # Batch: every FMP fact for the company once, matched in Python
        # instead of one query per SEC fact.
        fmp_by_key = {
            (fact.metric, fact.period): fact
            for fact in db.scalars(
                select(FinancialFact).where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.source_type == "FMP",
                )
            ).all()
        }
        for sec_fact in sec_facts:
            fmp_fact = fmp_by_key.get((sec_fact.metric, sec_fact.period))
            if fmp_fact is not None:
                sec_val = float(sec_fact.value)
                fmp_val = float(fmp_fact.value)
                diff = abs(sec_val - fmp_val) / max(abs(fmp_val), 1)
                if diff > 0.05:
                    pct = round(diff * 100, 1)
                    conflicts.append(
                        f"{sec_fact.metric}:{sec_fact.period} FMP={int(fmp_val)} SEC={int(sec_val)} diff={pct}%"
                    )

        document.metadata_ = {
            **(document.metadata_ or {}),
            "provider": "SEC",
            "cik": cik,
            "last_refreshed_at": datetime.now(UTC).isoformat(),
            "conflicts": conflicts,
        }
        # Hook gratuito best-effort (EDGAR 10-K/10-Q + FRED): una llamada que
        # nunca rompe el flujo principal de ingesta.
        try:
            free_data = await _free_data_snapshot(ticker, cik)
        except Exception:
            free_data = {"status": "unavailable", "recent_filings": [], "macro": None}
        document.metadata_ = {**(document.metadata_ or {}), "free_data": free_data}
        # Chunks RAG desde los hechos persistidos (ver refresh_from_esef).
        sync_company_fact_chunks(db, company)
        db.commit()

        return {
            "status": "ingested",
            "ticker": ticker,
            "provider": "SEC",
            "source_document_id": document.id,
            "facts_imported": facts_imported,
            "cik": cik,
            "conflicts": conflicts,
            "free_data": free_data,
        }

    async def refresh_from_esef(self, db: Session, company: Company) -> dict[str, Any]:
        """Fundamentales anuales IFRS desde el snapshot ESEF local (build_esef_snapshots).

        Solo hechos consolidados (entry["dims"] == []: los desgloses por miembro
        NUNCA se leen como total consolidado). Duraciones anuales (300-380 dias)
        para magnitudes de flujo; instantes para balance. Alias fusionados por
        periodo: gana el primer alias que informa el periodo, nunca se suman.
        """
        ticker = company.ticker.upper()
        snapshot = esef_connector.read_esef_snapshot(ticker)
        if snapshot is None:
            raise RuntimeError(f"Sin snapshot ESEF local para {ticker}: por ahora solo hay cobertura de emisores IBEX revisados")

        facts_data = snapshot.get("facts", {})
        document = self._source_document_esef(db, company, ticker, snapshot)
        self._replace_esef_data(db, company)
        facts_imported = 0

        for metric, concepts, unit in ESEF_METRIC_MAP:
            by_period: dict[str, dict[str, Any]] = {}
            for concept in concepts:
                entries = facts_data.get(concept, {}).get(unit, [])
                for entry in entries:
                    if entry.get("dims"):  # desglose por miembro: no es el consolidado
                        continue
                    if "end" in entry and "start" in entry:
                        try:
                            from datetime import date as _date

                            span = (_date.fromisoformat(entry["end"]) - _date.fromisoformat(entry["start"])).days
                        except (TypeError, ValueError):
                            continue
                        if not 300 <= span <= 380:
                            continue  # solo ejercicios anuales
                        period_date = str(entry["end"])
                    elif "instant" in entry:
                        period_date = str(entry["instant"])
                    else:
                        continue
                    if period_date not in by_period:  # primer alias que informa gana
                        by_period[period_date] = entry
            for period_date in sorted(by_period, reverse=True)[:10]:
                val = _decimal(by_period[period_date].get("val"))
                if val is None:
                    continue
                if metric == "capital_expenditure":
                    val = -val
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric=metric,
                        value=val,
                        unit="EUR/share" if unit.endswith("/xbrli:shares") else "EUR",
                        period=f"{period_date}:FY",
                        fiscal_year=int(period_date[:4]),
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="ESEF",
                        is_reported=True,
                        confidence=Decimal("0.95"),
                    )
                )
                facts_imported += 1

        db.flush()  # la sesion de ingestion usa autoflush=False: flush antes de derivar
        facts_imported += self._derive_esef_metrics(db, company, document)

        document.metadata_ = {
            **(document.metadata_ or {}),
            "provider": "ESEF",
            "lei": snapshot.get("lei"),
            "entity_name": snapshot.get("entity_name"),
            "period_end": snapshot.get("period_end"),
            "fxo_id": snapshot.get("fxo_id"),
            "snapshot_fetched_at": snapshot.get("fetched_at"),
            "last_refreshed_at": datetime.now(UTC).isoformat(),
        }
        # Chunks RAG desde los hechos persistidos (documento parseado no existe:
        # el snapshot es XBRL, no texto). Sin esto rebuild_tenant no indexa nada.
        sync_company_fact_chunks(db, company)
        db.commit()

        return {
            "status": "ingested",
            "ticker": ticker,
            "provider": "ESEF",
            "source_document_id": document.id,
            "facts_imported": facts_imported,
            "lei": snapshot.get("lei"),
            "period_end": snapshot.get("period_end"),
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
        tenant_id = db.info.get("tenant_id")
        fact_tenant = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        statement_tenant = (
            FinancialStatement.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialStatement.tenant_id.is_(None)
        )
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "FMP",
                fact_tenant,
            )
        )
        db.execute(
            delete(FinancialStatement).where(
                FinancialStatement.company_id == company.id,
                FinancialStatement.source_id == document.id,
                statement_tenant,
            )
        )
        db.flush()

    def _derive_sec_metrics(self, db: Session, company: Company, document: Document) -> int:
        """Metricas derivadas del XBRL bruto (la SEC publica componentes, no
        derivadas; FMP si las trae): FCF = OCF + capex (capex ya negativo),
        margen FCF, crecimiento de revenue y deuda neta, por ano fiscal.
        Sin ellas el snapshot de valoracion queda insufficient_data."""
        by_metric: dict[str, dict[int, FinancialFact]] = {}
        for fact in db.scalars(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "SEC",
                FinancialFact.is_reported.is_(True),
            )
        ):
            if fact.fiscal_year is not None:
                by_metric.setdefault(fact.metric, {})[fact.fiscal_year] = fact

        def year_fact(metric: str, year: int) -> FinancialFact | None:
            return by_metric.get(metric, {}).get(year)

        derived = 0
        years = sorted({y for metric_facts in by_metric.values() for y in metric_facts})
        for year in years:
            ocf = year_fact("operating_cash_flow", year)
            capex = year_fact("capital_expenditure", year)
            revenue = year_fact("revenue", year)
            debt = year_fact("total_debt", year)
            cash = year_fact("cash_and_equivalents", year)

            fcf: FinancialFact | None = None
            if ocf is not None and capex is not None:
                fcf = FinancialFact(
                    company_id=company.id,
                    metric="free_cash_flow",
                    value=ocf.value + capex.value,
                    unit="USD",
                    period=ocf.period,
                    fiscal_year=year,
                    fiscal_quarter="FY",
                    source_id=document.id,
                    source_type="SEC",
                    is_reported=False,
                    confidence=Decimal("0.85"),
                )
                db.add(fcf)
                derived += 1
            if (
                fcf is not None
                and revenue is not None
                and revenue.value > 0
            ):
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="fcf_margin",
                        value=fcf.value / revenue.value,
                        unit="decimal",
                        period=revenue.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="SEC",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1
            previous_revenue = year_fact("revenue", year - 1)
            if (
                revenue is not None
                and previous_revenue is not None
                and previous_revenue.value > 0
            ):
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="revenue_growth",
                        value=(revenue.value / previous_revenue.value) - 1,
                        unit="decimal",
                        period=revenue.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="SEC",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1
            if debt is not None and cash is not None:
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="net_debt",
                        value=debt.value - cash.value,
                        unit="USD",
                        period=debt.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="SEC",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1
        db.flush()
        return derived

    def _derive_esef_metrics(self, db: Session, company: Company, document: Document) -> int:
        """Metricas derivadas de los hechos ESEF, mismo contrato que
        _derive_sec_metrics: FCF = OCF + capex (capex ya negativo), margenes
        (bruto, operativo, neto, FCF), crecimiento de revenue, tipo impositivo
        efectivo y EBITDA = EBIT + D&A. is_reported=False: derivadas, nunca
        presentadas como reportadas. net_debt se omite a proposito: IFRS
        reparte borrowings current/noncurrent/lease y sumarlos esta
        prohibido (hueco honesto documentado en ESEF_METRIC_MAP)."""
        by_metric: dict[str, dict[int, FinancialFact]] = {}
        for fact in db.scalars(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "ESEF",
                FinancialFact.is_reported.is_(True),
            )
        ):
            if fact.fiscal_year is not None:
                by_metric.setdefault(fact.metric, {})[fact.fiscal_year] = fact

        def year_fact(metric: str, year: int) -> FinancialFact | None:
            return by_metric.get(metric, {}).get(year)

        def add_ratio(metric: str, numerator: FinancialFact, denominator: FinancialFact) -> int:
            if denominator.value is None or denominator.value <= 0:
                return 0
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=numerator.value / denominator.value,
                    unit="decimal",
                    period=numerator.period,
                    fiscal_year=numerator.fiscal_year,
                    fiscal_quarter="FY",
                    source_id=document.id,
                    source_type="ESEF",
                    is_reported=False,
                    confidence=Decimal("0.85"),
                )
            )
            return 1

        derived = 0
        years = sorted({y for metric_facts in by_metric.values() for y in metric_facts})
        for year in years:
            ocf = year_fact("operating_cash_flow", year)
            capex = year_fact("capital_expenditure", year)
            revenue = year_fact("revenue", year)
            net_income = year_fact("net_income", year)
            gross_profit = year_fact("gross_profit", year)
            operating_income = year_fact("operating_income", year)
            income_before_tax = year_fact("income_before_tax", year)
            income_tax_expense = year_fact("income_tax_expense", year)
            depreciation = year_fact("depreciation_amortization", year)

            fcf: FinancialFact | None = None
            if ocf is not None and capex is not None:
                fcf = FinancialFact(
                    company_id=company.id,
                    metric="free_cash_flow",
                    value=ocf.value + capex.value,
                    unit="EUR",
                    period=ocf.period,
                    fiscal_year=year,
                    fiscal_quarter="FY",
                    source_id=document.id,
                    source_type="ESEF",
                    is_reported=False,
                    confidence=Decimal("0.85"),
                )
                db.add(fcf)
                derived += 1
            if fcf is not None and revenue is not None and revenue.value > 0:
                derived += add_ratio("fcf_margin", fcf, revenue)
            previous_revenue = year_fact("revenue", year - 1)
            if (
                revenue is not None
                and previous_revenue is not None
                and previous_revenue.value > 0
            ):
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="revenue_growth",
                        value=(revenue.value / previous_revenue.value) - 1,
                        unit="decimal",
                        period=revenue.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="ESEF",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1
            if revenue is not None and revenue.value > 0:
                if gross_profit is not None:
                    derived += add_ratio("gross_margin", gross_profit, revenue)
                if operating_income is not None:
                    derived += add_ratio("operating_margin", operating_income, revenue)
                if net_income is not None:
                    derived += add_ratio("net_margin", net_income, revenue)
            if (
                income_tax_expense is not None
                and income_before_tax is not None
                and income_before_tax.value > 0
            ):
                derived += add_ratio("effective_tax_rate", income_tax_expense, income_before_tax)
            if operating_income is not None and depreciation is not None:
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="ebitda",
                        value=operating_income.value + depreciation.value,
                        unit="EUR",
                        period=operating_income.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="ESEF",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1
        db.flush()
        return derived

    def _source_document_sec(self, db: Session, company: Company, ticker: str) -> Document:
        title = f"SEC XBRL facts - {ticker}"
        document = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_type == "SEC",
                Document.title == title,
            )
        )
        if document:
            return document
        document = Document(
            company_id=company.id,
            title=title,
            source_type="SEC",
            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={ticker}&type=10-K",
            metadata_={"provider": "SEC", "normalized": True},
        )
        db.add(document)
        db.flush()
        return document

    def _source_document_esef(
        self, db: Session, company: Company, ticker: str, snapshot: dict[str, Any]
    ) -> Document:
        title = f"ESEF XBRL facts - {ticker}"
        document = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_type == "ESEF",
                Document.title == title,
            )
        )
        if document:
            return document
        document = Document(
            company_id=company.id,
            title=title,
            source_type="ESEF",
            source_url=f"https://filings.xbrl.org/api/filings (fxo_id={snapshot.get('fxo_id')})",
            metadata_={"provider": "ESEF", "normalized": True},
        )
        db.add(document)
        db.flush()
        return document

    def _replace_esef_data(self, db: Session, company: Company) -> None:
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "ESEF",
                tenant_filter,
            )
        )

    def _replace_sec_data(self, db: Session, company: Company) -> None:
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "SEC",
                tenant_filter,
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

    def _add_profile_facts(
        self,
        db: Session,
        company: Company,
        document: Document,
        profile: list[dict[str, Any]],
    ) -> int:
        if not profile:
            return 0
        row = profile[0]
        period = datetime.now(UTC).date().isoformat()
        count = 0
        for metric, field, unit in [
            ("beta", "beta", "decimal"),
            ("market_cap", "mktCap", "USD"),
        ]:
            value = _decimal(row.get(field))
            if value is None:
                continue
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=value,
                    unit=unit,
                    period=period,
                    source_id=document.id,
                    source_type="FMP_profile",
                    is_reported=True,
                    is_adjusted=False,
                    confidence=Decimal("0.75"),
                )
            )
            count += 1
        return count
