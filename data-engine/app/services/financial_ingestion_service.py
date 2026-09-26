from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import redact_secrets
from app.models import Company, Document, FinancialFact, FinancialStatement, MarketPrice
from app.services.connectors import esef as esef_connector
from app.services.connectors import fred as fred_connector
from app.services.connectors import sec_edgar as sec_edgar_connector
from app.services.connectors.fmp import FMPClient
from app.services.connectors.sec import SECClient
from app.services.fact_chunk_service import sync_company_fact_chunks

MetricSpec = tuple[str, str, str]

# Concepts that are DISJOINT PARTS of one total, not alternative tags for it.
# Treating them as aliases meant whichever happened to be filed last won, so an
# issuer with 5.000 of finite-lived and 8.000 of indefinite-lived intangibles
# stored only one of the two and the metric silently changed meaning between
# years. These are summed per period instead.
SEC_INTANGIBLE_COMPONENTS = [
    "FiniteLivedIntangibleAssetsNet",
    "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
]
# Metrics whose concepts are disjoint parts to be summed, not alternative tags.
SUMMED_COMPONENT_METRICS: frozenset[str] = frozenset({"intangible_assets"})

# Which provider wins when the same (metric, fiscal year) exists more than once.
# A regulator filing the number itself beats a vendor's restatement of it, and
# a vendor beats a manually typed value, which beats an unattributed row.
# Without this, `created_at` decided ownership and the DCF could be anchored on
# whichever provider happened to be ingested last.
SOURCE_PRIORITY: dict[str, int] = {
    "SEC": 0,
    "ESEF": 0,
    "CNMV": 0,
    "FMP": 10,
    "FMP_profile": 20,
}


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
    # Orden por alcance, NO por antiguedad: el tag combinado (largo + corto) es
    # el que representa "deuda total", y se coloco antes detras de
    # LongTermDebt, asi que la deuda neta salia sin la parte corriente. El
    # ganador lo decide el `filed` mas reciente del MISMO periodo, de modo que el
    # orden solo desempata cuando el emisor nunca presenta el tag combinado.
    ("total_debt",        ["DebtLongtermAndShorttermCombinedAmount", "LongTermDebt", "LongTermDebtNoncurrent"], "USD"),
    ("total_assets",      ["Assets"],                                                                               "USD"),
    ("total_liabilities", ["Liabilities"],                                                                          "USD"),
    # StockholdersEquity = patrimonio atribuible a la matriz; la variante
    # "IncludingPortionAttributableToNoncontrollingInterest" consolida los
    # intereses minoritarios. Son MAGNITUDES DISTINTAS: mezclarlas hacia que el
    # balance cuadre por la diferencia de NCI. Se usa la de la matriz.
    ("total_equity",      ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "USD"),
    ("goodwill",          ["Goodwill"],                                                                              "USD"),
    ("intangible_assets", SEC_INTANGIBLE_COMPONENTS,                                                                "USD"),
    ("operating_lease_liabilities", ["OperatingLeaseLiability", "OperatingLeaseLiabilityNoncurrent"],                "USD"),
    ("operating_cash_flow", ["NetCashProvidedByUsedInOperatingActivities"],                                         "USD"),
    ("capital_expenditure", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],          "USD"),
    ("depreciation_amortization", ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                                   "Depreciation", "DepreciationAndAmortization"],                                                                  "USD"),
    ("dividends_paid",    ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],                                "USD"),
]


# IFRS (ESEF) -> metricas internas. Mismo contrato que SEC con una diferencia
# que importa: aqui los snapshots no llevan fecha de presentacion, asi que no
# hay nada honesto con lo que ordenar dos tags y gana el primero declarado. Los
# tags que NO son alias sino partes disjuntas de un total (capex desagregado)
# se suman, y un total yaAgglomerado nunca se suma con sus propias partes; ver
# ESEF_PART_CONCEPTS y ESEF_SUPERSET_CONCEPTS. Solo conceptos verificados en
# los snapshots reales de los 6 emisores reviewed (24-25/9); ampliado 25/9 con
# componentes de deuda verificados en 105 emisores (27+ con
# CurrentFinancialLiabilities). Hueco honesto: shares_diluted (ninguno de los 6
# reviewed trae WeightedAverageNumberOfShares en base scope). EBITDA no es tag
# IFRS estandar: se deriva como operating_income + D&A en _derive_esef_metrics
# (no aplica a bancos sin beneficio operativo, p.ej. SAN).
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
    # Componentes de deuda financiera (no alias: partes disjuntas del pasivo
    # financiero). total_debt se DERIVE como suma declarada en _derive_esef_metrics.
    ("financial_liabilities_current", ["ifrs-full:CurrentFinancialLiabilities"],                          "iso4217:EUR"),
    ("financial_liabilities_noncurrent", ["ifrs-full:NoncurrentFinancialLiabilities"],                    "iso4217:EUR"),
    ("lease_liabilities_current", ["ifrs-full:CurrentLeaseLiabilities"],                                  "iso4217:EUR"),
    ("lease_liabilities_noncurrent", ["ifrs-full:NoncurrentLeaseLiabilities"],                            "iso4217:EUR"),
    ("operating_cash_flow", ["ifrs-full:CashFlowsFromUsedInOperatingActivities"],                        "iso4217:EUR"),
    ("capital_expenditure", ["ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                             "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
                             # Concepto combinado estandar IFRS (PP&E + intangibles + otras no
                             # corrientes): lo usan emisores que no desagregan el capex, p.ej. REP.
                             "ifrs-full:PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"],
                                                                                                        "iso4217:EUR"),
    ("dividends_paid",    ["ifrs-full:DividendsPaidClassifiedAsFinancingActivities"],                    "iso4217:EUR"),
]

# ESEF: concepts that are disjoint PARTS of one total. A filer that discloses
# capex disaggregated reports PP&E and intangibles separately, and taking the
# first alias that reports leaves half the capex out: FCF that is too high and a
# DCF that is too generous. These are added up per period.
ESEF_PART_CONCEPTS: dict[str, list[str]] = {
    "capital_expenditure": [
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
    ],
}
# ESEF: concepts that ALREADY include the parts above. Summing a total with its
# own components is the double count this table prevents: a filer that tags the
# combined concept (REP) is taken at its word, and only filers that disclose
# the parts get them added up.
ESEF_SUPERSET_CONCEPTS: dict[str, list[str]] = {
    "capital_expenditure": [
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwill"
        "InvestmentPropertyAndOtherNoncurrentAssets",
    ],
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def is_summed_component(metric: str) -> bool:
    """True when a metric's concepts are disjoint PARTS of one total."""
    return metric in SUMMED_COMPONENT_METRICS


def _collapse_aliases(
    by_concept: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """One winner per period across concepts that are ALIASES of each other.

    Many filers migrate from one tag to another and freeze the old one in the
    past, so the same period arrives under two concepts. That is one fact
    reported twice, and the most recent ``filed`` is its current presentation
    (a recast included). These concepts are alternatives, never added up.
    """
    by_end: dict[str, dict[str, Any]] = {}
    for entries in by_concept.values():
        for entry in entries.values():
            end = str(entry.get("end") or "")
            current = by_end.get(end)
            if current is None or str(entry.get("filed") or "") > str(
                current.get("filed") or ""
            ):
                by_end[end] = entry
    return by_end


def _sum_disjoint_components(
    by_concept: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Add up per-period values of concepts that are parts of the same total.

    Takes the concepts APART on purpose. The previous shape was a flat
    ``{end: entry}`` map, which had already collapsed the parts of a period
    into a single winner before this function ever saw them, so a total like
    intangible assets stored whichever component was filed last and quietly
    dropped the other: the metric changed meaning between years and no amount
    of summing downstream could recover it.

    The merged row keeps the most recent ``filed`` for provenance and records
    every contributing concept in ``_components``, so the total stays auditable
    back to its parts instead of becoming an opaque number.
    """
    totals: dict[str, dict[str, Any]] = {}
    for concept, entries in by_concept.items():
        for end, entry in entries.items():
            value = _decimal(entry.get("val"))
            if value is None:
                continue
            bucket = totals.setdefault(
                end,
                {
                    "val": Decimal("0"),
                    "filed": "",
                    "end": end,
                    "_components": {},
                    "_latest": entry,
                },
            )
            bucket["val"] = bucket["val"] + value
            bucket["_components"][concept] = str(value)
            filed = str(entry.get("filed") or "")
            if filed > str(bucket["filed"]):
                bucket["filed"] = filed
                # The label of the merged row (`fp`, `accn`, `form`) comes from
                # the newest filing of the period, not from whichever part was
                # summed first.
                bucket["_latest"] = entry
    for key, bucket in list(totals.items()):
        latest = bucket.pop("_latest")
        merged = {**latest, **bucket}
        if len(merged["_components"]) == 1:
            merged["_concept"] = next(iter(merged["_components"]))
        else:
            merged["_concept"] = "+".join(sorted(merged["_components"]))
        merged["val"] = float(merged["val"])
        totals[key] = merged
    return totals


def _merge_for_metric(
    by_concept: dict[str, dict[str, dict[str, Any]]], metric: str
) -> dict[str, dict[str, Any]]:
    """Merge concepts per period: summed when they are parts, else one winner."""
    if is_summed_component(metric):
        return _sum_disjoint_components(by_concept)
    return _collapse_aliases(by_concept)


def _collect_by_concept(
    us_gaap: dict[str, Any],
    concepts: list[str],
    unit_key: str,
    *,
    forms: set[str],
    periods: set[str],
    min_span: int | None,
    max_span: int | None,
    modal_month: str | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Newest ``filed`` fact per concept and period, before any merging.

    Keeping the concepts apart until the caller knows what they are (aliases or
    disjoint parts) is what lets `_collapse_aliases` and
    `_sum_disjoint_components` disagree on purpose instead of by accident.
    """
    by_concept: dict[str, dict[str, dict[str, Any]]] = {}
    for concept in concepts:
        entries = us_gaap.get(concept, {}).get("units", {}).get(unit_key, [])
        for entry in entries:
            if entry.get("form") not in forms or entry.get("fp") not in periods:
                continue
            # A flow fact (one WITH `start`) has to really span the period it
            # claims: `fp="FY"` does not guarantee an annual duration, and the
            # year-to-date and TTM variants clear a duration check too. Instant
            # facts (balance sheet, no `start`) are not duration-filtered.
            start = entry.get("start")
            if start and min_span is not None and max_span is not None:
                try:
                    span = (
                        date.fromisoformat(str(entry["end"]))
                        - date.fromisoformat(str(start))
                    ).days
                except (KeyError, TypeError, ValueError):
                    continue
                if not min_span <= span <= max_span:
                    continue
                # The duration check alone is not enough: the ~365-day TTM
                # rows that close on a quarter end pass it. Only the issuer's
                # modal fiscal close month enters an annual fact.
                if modal_month and str(entry.get("end") or "")[5:7] != modal_month:
                    continue
            end = str(entry.get("end") or "")
            if not end:
                continue
            concept_entries = by_concept.setdefault(concept, {})
            current = concept_entries.get(end)
            if current is None or str(entry.get("filed") or "") > str(
                current.get("filed") or ""
            ):
                concept_entries[end] = {**entry, "_concept": concept}
    return by_concept


def _esef_period(entry: dict[str, Any]) -> str | None:
    """The period an ESEF fact belongs to, or None when it is not usable.

    A per-member breakdown is not the consolidated figure, and a flow fact
    only counts when it really spans the fiscal year it claims.
    """
    if entry.get("dims"):
        return None
    if "end" in entry and "start" in entry:
        try:
            span = (
                date.fromisoformat(str(entry["end"]))
                - date.fromisoformat(str(entry["start"]))
            ).days
        except (TypeError, ValueError):
            return None
        if not 300 <= span <= 380:
            return None
        return str(entry["end"])
    if "instant" in entry:
        return str(entry["instant"])
    return None


def _merge_esef_periods(
    facts_data: dict[str, Any], concepts: list[str], unit: str, metric: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """One value per period for an ESEF metric, plus an explicit coverage record.

    A filer that disaggregates a total into disjoint parts has them added up, a
    filer that tags the combined total is taken at its word, and everything
    else keeps the first concept that reports the period: ESEF snapshots carry
    no filing date, so there is nothing honest to rank two aliases with beyond
    the order the concepts are declared in.

    Two failure modes of the sum are refused rather than published:

    * the same fact twice (same tag, same context, same value) used to be added
      twice - two snapshots of one filing read as double the capex. Identical
      duplicates collapse to one fact; two DIFFERENT values for the same tag
      and period cannot be ranked without a filing date, so the period is
      ambiguous and is rejected (a disclosed total for the period still wins);
    * a part that is missing for the period used to vanish silently, and the
      subtotal was published as the complete metric. A missing part is only
      declared when its absence can be affirmed - the filer DOES report that
      concept, just not for this period; a part the filer never reports can be
      zero or not applicable, and the sum is taken as complete.

    Returns the merged periods and a coverage record with the rejected
    (ambiguous) and incomplete (partial) periods, so the caller can state what
    was NOT published instead of letting it pass for the whole magnitude.
    """
    superset = ESEF_SUPERSET_CONCEPTS.get(metric, [])
    parts = ESEF_PART_CONCEPTS.get(metric, [])
    by_period: dict[str, dict[str, Any]] = {}
    part_facts: dict[str, dict[str, set[Decimal]]] = {}
    concepts_with_data: set[str] = set()
    for concept in concepts:
        for entry in facts_data.get(concept, {}).get(unit, []):
            period = _esef_period(entry)
            if period is None:
                continue
            if concept in superset:
                by_period.setdefault(period, entry)
            elif concept in parts:
                value = _decimal(entry.get("val"))
                if value is None:
                    continue
                concepts_with_data.add(concept)
                part_facts.setdefault(period, {}).setdefault(concept, set()).add(value)
            elif period not in by_period:
                by_period[period] = entry
    coverage: dict[str, Any] = {"ambiguous": {}, "partial": {}}
    for period, by_concept in part_facts.items():
        # A disclosed total always beats the sum of its parts: it is the only
        # statement of the whole magnitude, and it may include components the
        # parts do not itemise.
        if period in by_period:
            continue
        conflicts = {
            concept: sorted(str(value) for value in values)
            for concept, values in by_concept.items()
            if len(values) > 1
        }
        if conflicts:
            coverage["ambiguous"][period] = conflicts
            continue
        missing = sorted(concepts_with_data - set(by_concept))
        if missing:
            coverage["partial"][period] = missing
            continue
        by_period[period] = {
            "val": float(sum((next(iter(values)) for values in by_concept.values()), Decimal("0"))),
            "period": period,
            "_components": {
                concept: str(next(iter(values))) for concept, values in by_concept.items()
            },
        }
    return by_period, coverage


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
        snapshot["filings_error"] = redact_secrets(str(exc))[:200]
    try:
        snapshot["macro"] = await fred_connector.latest_observation("cpi")
    except Exception as exc:  # pragma: no cover - red defensiva
        snapshot["macro"] = None
        snapshot["macro_error"] = redact_secrets(str(exc))[:200]
    return snapshot


def _modal_fiscal_end_month(us_gaap: dict[str, Any]) -> str | None:
    """Mes modal de cierre de ejercicio a partir de TODOS los hechos de flujo
    anuales candidatos (300-380 dias, fp=FY, 10-K/20-F). Los acumulados TTM de
    ~365 dias que cierran en fin de trimestre (caso real AA/AAL: revenue
    2019-04-01 -> 2020-03-31 etiquetado FY) pasan el filtro de duracion, pero
    su mes de cierre es minoritario frente al del ejercicio real. Modalidad por
    MES (no por dia exacto) para absorber el drift de ejercicios de 52/53
    semanas (AAPL cierra el ultimo sabado de septiembre: 09-25, 09-26, 09-28).
    Devuelve None si no hay candidatos de flujo (emisor sin historia anual).
    """
    counts: Counter[str] = Counter()
    latest_end: dict[str, str] = {}
    for _metric, concepts, unit in SEC_METRIC_MAP:
        xbrl_unit_key = "USD/shares" if unit == "USD/share" else unit
        for concept in concepts:
            entries = us_gaap.get(concept, {}).get("units", {}).get(xbrl_unit_key, [])
            for e in entries:
                if e.get("fp") != "FY" or e.get("form") not in {"10-K", "20-F"}:
                    continue
                start = e.get("start")
                if not start:
                    continue
                try:
                    span = (date.fromisoformat(str(e["end"])) - date.fromisoformat(str(start))).days
                except (TypeError, ValueError):
                    continue
                if not 300 <= span <= 380:
                    continue
                end = str(e.get("end") or "")
                if len(end) < 7:
                    continue
                month = end[5:7]
                counts[month] += 1
                if end > latest_end.get(month, ""):
                    latest_end[month] = end
    if not counts:
        return None
    # Empate: gana el mes con el cierre mas reciente (ejercicio actual).
    return max(counts, key=lambda m: (counts[m], latest_end.get(m, "")))


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
        self._replace_sec_data(db, company, document)

        facts_imported = 0
        cash_restricted_years: set[int] = set()
        concept_usage: dict[str, dict[str, Any]] = {}
        modal_fy_month = _modal_fiscal_end_month(us_gaap)

        for metric, concepts, unit in SEC_METRIC_MAP:
            xbrl_unit_key = "USD/shares" if unit == "USD/share" else unit
            # --- Trimestres (10-Q): mismas reglas de fusion por `end` ---
            # fp Q1-Q4 + form 10-Q; flujo = 70-110 dias (trimestre real; los
            # acumulados YTD de ~180 dias y los TTM quedan fuera); instantaneos
            # (balance, sin start) pasan. fiscal_year queda NULL a proposito:
            # los consumidores anuales seleccionan por fiscal_year (y los que
            # ordenan por el usan nullslast), asi las filas :Qn nunca se
            # confunden con el ejercicio anual. period = "<end>:Q<n>".
            by_end_q = _merge_for_metric(
                _collect_by_concept(
                    us_gaap,
                    concepts,
                    xbrl_unit_key,
                    forms={"10-Q"},
                    periods={"Q1", "Q2", "Q3", "Q4"},
                    min_span=70,
                    max_span=110,
                ),
                metric,
            )
            if by_end_q:
                q_sorted = sorted(
                    by_end_q.values(), key=lambda e: str(e["end"]), reverse=True
                )[:12]
                for entry in q_sorted:
                    val = _decimal(entry.get("val"))
                    if val is None:
                        continue
                    if metric == "capital_expenditure":
                        val = -val
                    fp = str(entry["fp"])
                    db.add(
                        FinancialFact(
                            company_id=company.id,
                            metric=metric,
                            value=val,
                            unit=unit,
                            period=f"{entry['end']}:{fp}",
                            fiscal_year=None,
                            fiscal_quarter=fp,
                            source_id=document.id,
                            source_type="SEC",
                            is_reported=True,
                            confidence=Decimal("0.9"),
                        )
                    )
                    facts_imported += 1
            # Los alias se FUSIONAN, no "gana el primero que informe": muchos
            # filers migraron de tag (Revenues -> SalesRevenueNet ->
            # RevenueFromContractWithCustomer...) y el tag antiguo queda
            # congelado en el pasado. Fusion por periodo (`end`) conservando
            # el `filed` mas reciente: mismo periodo bajo dos tags = una sola
            # vez, con su presentacion mas reciente (recast incluido).
            # OJO: `fy` es el ANIO DEL FILING, no el del periodo. Un 10-K de
            # FY2025 trae revenue de 2025, 2024 y 2023; el ano fiscal correcto
            # es el del `end`. Ante re-presentaciones del mismo periodo manda
            # el `filed` mas reciente, pero DENTRO de cada tag: comparar tags
            # distintos entre si es lo que descartaba una de las partes de
            # `intangible_assets` en vez de sumarlas.
            by_end = _merge_for_metric(
                _collect_by_concept(
                    us_gaap,
                    concepts,
                    xbrl_unit_key,
                    forms={"10-K", "20-F"},
                    periods={"FY"},
                    min_span=300,
                    max_span=380,
                    modal_month=modal_fy_month,
                ),
                metric,
            )
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
                    # Record which XBRL concept produced the value. Several
                    # metrics accept alternative tags with different scopes, so
                    # without this the definition of a series can change between
                    # years with nothing in the database saying so. The map is
                    # written to the document below (FinancialFact has no
                    # free-form column, and this is per-run provenance).
                    concept_usage.setdefault(metric, {})[str(entry["end"])] = entry.get(
                        "_concept"
                    )
                    facts_imported += 1

        if concept_usage:
            existing_meta = dict(document.metadata_ or {})
            existing_meta["xbrl_concept_by_metric_period"] = concept_usage
            document.metadata_ = existing_meta

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
        self._replace_esef_data(db, company, document)
        facts_imported = 0

        esef_coverage: dict[str, Any] = {}
        for metric, concepts, unit in ESEF_METRIC_MAP:
            by_period, coverage = _merge_esef_periods(facts_data, concepts, unit, metric)
            if coverage["ambiguous"] or coverage["partial"]:
                esef_coverage[metric] = coverage
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
            "esef_coverage": esef_coverage,
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
        """Latest fact for a metric, preferring the authoritative source.

        Ordering by ``created_at`` alone meant whichever provider was ingested
        last owned the metric: after a ``refresh_from_fmp`` on top of SEC, the
        DCF anchor could be the vendor's revenue while the primary filing sat
        ignored, with nothing in the trace saying so. The priority makes the
        choice deterministic and the provenance auditable.
        """
        rows = list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(
                    FinancialFact.fiscal_year.desc().nullslast(),
                    FinancialFact.created_at.desc(),
                    FinancialFact.id.desc(),
                )
            ).all()
        )
        if not rows:
            return None
        latest_year = rows[0].fiscal_year
        candidates = [row for row in rows if row.fiscal_year == latest_year]
        return min(
            candidates,
            key=lambda row: (SOURCE_PRIORITY.get(row.source_type or "", 50), row.id),
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
        efectivo y EBITDA = EBIT + D&A. total_debt = financial_liabilities_current
        + financial_liabilities_noncurrent, SOLO cuando ambos componentes
        existen ese ejercicio (son partes disjuntas del pasivo financiero, no
        alias: la suma es contablemente correcta y queda declarada aqui).
        is_reported=False: derivadas, nunca presentadas como reportadas."""
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
            fl_current = year_fact("financial_liabilities_current", year)
            fl_noncurrent = year_fact("financial_liabilities_noncurrent", year)

            if fl_current is not None and fl_noncurrent is not None:
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric="total_debt",
                        value=fl_current.value + fl_noncurrent.value,
                        unit="EUR",
                        period=fl_current.period,
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="ESEF",
                        is_reported=False,
                        confidence=Decimal("0.85"),
                    )
                )
                derived += 1

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

    def _replace_esef_data(self, db: Session, company: Company, document: Document) -> None:
        """Delete only the facts THIS document wrote (see ``_replace_sec_data``)."""
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_id == document.id,
                tenant_filter,
            )
        )

    def _replace_sec_data(self, db: Session, company: Company, document: Document) -> None:
        """Delete only the facts THIS document wrote.

        The filter used to be ``source_type == "SEC"``, which is not an
        ownership boundary: ``kpi_extraction_service.approve()`` writes
        human-approved canonical facts carrying the ingested document's
        ``source_type``, and ``thesis_evidence_service`` writes evidence facts
        with its own document. A fundamentals refresh therefore deleted
        reviewer-approved values with no trace, and left the two services
        fighting over the same rows.
        """
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        db.execute(
            delete(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_id == document.id,
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
