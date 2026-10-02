"""Valuation engine registry — resolve company.valuation_model to an engine."""

from __future__ import annotations

from app.models import Company
from app.valuation.engines.base import ValuationEngine
from app.valuation.engines.commodity import CommodityCycleEngine
from app.valuation.engines.ddm_fcfe import DividendDiscountEngine, FreeCashFlowToEquityEngine
from app.valuation.engines.holding_company import HoldingCompanyEngine
from app.valuation.engines.pre_revenue import PreRevenueScenarioEngine
from app.valuation.engines.relative_multiples import RelativeMultiplesEngine
from app.valuation.engines.sector_specific import (
    BankValuationEngine,
    InsurerValuationEngine,
    ReitValuationEngine,
)
from app.valuation.engines.sotp_engine import SOTPEngine
from app.valuation.engines.standard_dcf import StandardDCFEngine
from app.valuation.engines.utilities import RegulatedUtilityEngine

VALUATION_ENGINES: dict[str, type[ValuationEngine]] = {
    "standard_dcf": StandardDCFEngine,
    "sotp": SOTPEngine,
    "pre_revenue": PreRevenueScenarioEngine,
    "holding_company": HoldingCompanyEngine,
    "commodity": CommodityCycleEngine,
    "bank": BankValuationEngine,
    "insurer": InsurerValuationEngine,
    "reit": ReitValuationEngine,
    "ddm": DividendDiscountEngine,
    "fcfe": FreeCashFlowToEquityEngine,
    "utilities": RegulatedUtilityEngine,
    "relative": RelativeMultiplesEngine,
}


def resolve_engine_key(company: Company) -> str:
    model = (company.valuation_model or "").lower()
    tags = set(company.factor_tags or [])
    company_type = (company.company_type or "").lower()

    if (
        "utility" in company_type
        or "regulated" in company_type
        or "utilities" in company_type
        or "utilities" in tags
    ):
        return "utilities"
    if (
        "sotp" in model
        or "sotp" in tags
        or "holding" in company_type
        or "asset_manager" in company_type
    ):
        if "holding" in company_type or "asset_manager" in company_type:
            return "holding_company"
        return "sotp"
    if "commodity" in model or "commodities" in tags or "mining" in company_type or "uranium" in company_type:
        return "commodity"
    if (
        "pre_fcf" in tags
        or "speculative" in tags
        or "pre_revenue" in company_type
        or "speculative" in model
        or "nav_rough" in model
        or "probability_weighted_scenarios" in model
    ):
        return "pre_revenue"
    if "bank" in company_type or model.startswith("bank"):
        return "bank"
    if "insurer" in company_type or "insurance" in company_type:
        return "insurer"
    if "reit" in company_type:
        return "reit"
    if "dividend_discount" in model or "ddm" in model or "dividend_valuation" in tags:
        return "ddm"
    if "fcfe" in model or "equity_cash_flow" in model or "fcfe_valuation" in tags:
        return "fcfe"
    if "relative" in model or "peer_multiple" in model or "relative_valuation" in tags:
        return "relative"
    return "standard_dcf"


def resolve(company: Company) -> ValuationEngine:
    key = resolve_engine_key(company)
    engine_cls = VALUATION_ENGINES.get(key, StandardDCFEngine)
    return engine_cls()


def list_engines() -> list[str]:
    return sorted(VALUATION_ENGINES.keys())
