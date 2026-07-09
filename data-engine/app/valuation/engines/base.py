"""Valuation engine contracts and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company
from app.valuation.financial_snapshot import FinancialSnapshot, FinancialSnapshotBuilder
from app.valuation.moat_framework import empty_moat_framework


MODEL_VERSION = "valuation-engines-v1"


@dataclass
class ValuationContext:
    db: Session
    company: Company
    snapshot: FinancialSnapshot
    current_price: float | None
    engine_key: str


def insufficient_result(
    *,
    ticker: str,
    model_type: str,
    engine_key: str,
    current_price: float | None,
    missing_inputs: list[str],
    reason: str,
    snapshot: FinancialSnapshot | None = None,
    extra_trace: dict | None = None,
) -> dict:
    trace: dict[str, Any] = {
        "method": model_type,
        "engine": engine_key,
        "input_source": "insufficient_data",
        "publishable": False,
        "status": "insufficient_data",
        "missing_inputs": missing_inputs,
        "reason": reason,
        "model_version": MODEL_VERSION,
        "fact_ids": snapshot.fact_ids() if snapshot else {},
        "periods": snapshot.periods() if snapshot else {},
        "snapshot": {
            "as_of": snapshot.as_of_period if snapshot else None,
            "income_statement": snapshot.income_statement if snapshot else None,
            "balance_sheet": snapshot.balance_sheet if snapshot else None,
            "shares": snapshot.shares_period if snapshot else None,
            "warnings": snapshot.warnings if snapshot else [],
        },
    }
    if extra_trace:
        trace.update(extra_trace)

    return {
        "ticker": ticker,
        "model_type": model_type,
        "status": "insufficient_data",
        "publishable": False,
        "current_price": current_price,
        "bear_value": None,
        "base_value": None,
        "bull_value": None,
        "expected_value": None,
        "margin_of_safety": None,
        "missing_inputs": missing_inputs,
        "reverse_dcf": {},
        "sensitivity": {"rows": []},
        "trace": trace,
        "moat": empty_moat_framework(
            # company fields filled by caller via extra if needed
            "",
            [],
            [],
        ),
    }


class ValuationEngine(ABC):
    key: str = "base"

    @abstractmethod
    def value(self, context: ValuationContext) -> dict:
        raise NotImplementedError

    def build_context(
        self,
        db: Session,
        company: Company,
        current_price: float | None,
    ) -> ValuationContext:
        snapshot = FinancialSnapshotBuilder().build(db, company)
        return ValuationContext(
            db=db,
            company=company,
            snapshot=snapshot,
            current_price=current_price,
            engine_key=self.key,
        )


def default_growth(company: Company) -> float:
    tags = company.factor_tags or []
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.20
    if "software" in tags or "ai" in tags:
        return 0.10
    if "commodities" in tags:
        return 0.04
    return 0.07


def default_wacc(company: Company) -> float:
    tags = company.factor_tags or []
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.13
    if "commodities" in tags or "china" in tags:
        return 0.11
    if "quality" in tags:
        return 0.085
    return 0.10


def default_terminal_growth(company: Company) -> float:
    tags = company.factor_tags or []
    if "commodities" in tags:
        return 0.015
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.025
    return 0.03


def margin_of_safety(expected_value: float | None, current_price: float | None) -> float | None:
    if expected_value is None or current_price is None or current_price <= 0:
        return None
    return expected_value / current_price - 1
