"""Dedicated fact-driven valuation engines for financials and REITs.

Supuestos por motor (todos con inputs 100% de FinancialFact, sin bootstrap):

- BankValuationEngine: modelo de price-to-book justificado ``P/B = (ROE - g) /
  (CoE - g)`` con P/B acotado a [0.25, 3.0]. Supuestos: ``book_per_share`` =
  tangible book / acciones diluidas; ``g`` = crecimiento del book value
  (financial_facts, o 0.0 por política explícita si falta); escenarios
  bear/base/bull mueven ROE ±(2.5-3pp), CoE ∓(1-1.5pp) y g ∓1pp/+0.5pp.
  Sensibilidad: tabla de 3 filas variando CoE (-1pp / base / +1.5pp).
- InsurerValuationEngine: mismo P/B justificado multiplicado por un factor de
  calidad de suscripción ``clamp(1 + (1 - combined_ratio) * 2, 0.75, 1.25)``.
  Supuestos: ROE, CoE y combined ratio de facts; escenarios mueven ROE
  ±(2-2.5pp), CoE ∓(1-1.5pp) y combined ratio ±(2.5-3pp).
  Sensibilidad: tabla de 3 filas variando CoE.
- ReitValuationEngine: NAV directo ``(NOI / cap_rate - net_debt) / acciones``.
  Supuestos: cap rate de mercado de facts (debe ser > 0); escenarios mueven
  NOI ×(0.94/1.0/1.06) y cap rate ∓(50-75bp). Sensibilidad: tabla de 3 filas
  variando cap rate (-50bp / base / +75bp).

Probabilidades: ``source_confidence_plus_company_quality`` — peso base de la
confianza media de los facts de origen más una señal direccional propia de
cada motor (spread ROE-CoE en bancos, 1-combined_ratio en aseguradoras,
-cap_rate en REITs).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select

from app.models import FinancialFact
from app.valuation.engines.base import (
    MODEL_VERSION,
    ValuationContext,
    ValuationEngine,
    insufficient_result,
    margin_of_safety,
)
from app.valuation.moat_framework import empty_moat_framework


@dataclass(frozen=True)
class SourcedValue:
    value: float
    fact_id: int
    period: str
    confidence: float


def _latest(context: ValuationContext, *metrics: str) -> SourcedValue | None:
    fact = context.db.scalar(
        select(FinancialFact)
        .where(
            FinancialFact.company_id == context.company.id,
            FinancialFact.metric.in_(metrics),
        )
        .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
        .limit(1)
    )
    if fact is None:
        return None
    return SourcedValue(float(fact.value), fact.id, fact.period, float(fact.confidence))


def _probabilities(values: list[SourcedValue], directional_quality: float = 0.0) -> dict[str, float]:
    confidence = sum(value.confidence for value in values) / len(values)
    base = max(0.40, min(0.64, 0.38 + confidence * 0.26))
    upside_share = max(0.35, min(0.65, 0.50 + directional_quality * 0.25))
    tail = 1.0 - base
    bull = tail * upside_share
    return {"bear": tail - bull, "base": base, "bull": bull}


def _pb_sensitivity_rows(
    *,
    book_per_share: float,
    roe: float,
    cost_of_equity: float,
    growth: float,
    underwriting_factor: float = 1.0,
) -> dict:
    """Tabla de sensibilidad 1-D sobre el coste del equity (±100bp/±150bp).

    Revalúa el P/B justificado ``(ROE - g) / (CoE - g)`` acotado a [0.25, 3.0]
    en tres puntos de CoE; el resto de supuestos (ROE, g, factor de
    suscripción en aseguradoras) se mantiene en base. Devuelve el formato
    estándar ``{"rows": [...], "trace": {...}}``.
    """
    rows = []
    for label, cost in (
        ("low_coe", max(cost_of_equity - 0.01, growth + 0.005)),
        ("base_coe", cost_of_equity),
        ("high_coe", cost_of_equity + 0.015),
    ):
        justified_pb = max(0.25, min(3.0, (roe - growth) / (cost - growth)))
        rows.append(
            {
                "scenario": label,
                "cost_of_equity": cost,
                "roe": roe,
                "growth": growth,
                "justified_pb": justified_pb,
                "value_per_share": book_per_share * justified_pb * underwriting_factor,
            }
        )
    return {"rows": rows, "trace": {"method": "pb_cost_of_equity_sensitivity"}}


def _reit_sensitivity_rows(
    *,
    noi: float,
    cap_rate: float,
    net_debt: float,
    shares: float,
) -> dict:
    """Tabla de sensibilidad 1-D sobre el cap rate (-50bp / base / +75bp).

    Revalúa ``(NOI / cap_rate - net_debt) / acciones`` con el NOI base;
    el suelo de cap rate es 0.001 para evitar división por cero.
    """
    rows = []
    for label, cap in (
        ("low_cap_rate", max(cap_rate - 0.005, 0.001)),
        ("base_cap_rate", cap_rate),
        ("high_cap_rate", cap_rate + 0.0075),
    ):
        rows.append(
            {
                "scenario": label,
                "cap_rate": cap,
                "noi": noi,
                "value_per_share": max(0.0, noi / cap - net_debt) / shares,
            }
        )
    return {"rows": rows, "trace": {"method": "reit_cap_rate_sensitivity"}}


def _result(
    context: ValuationContext,
    *,
    engine_key: str,
    scenario_values: dict[str, float],
    probabilities: dict[str, float],
    fact_ids: dict[str, int],
    periods: dict[str, str],
    assumptions: dict,
    sensitivity: dict | None = None,
) -> dict:
    expected = sum(scenario_values[name] * probabilities[name] for name in scenario_values)
    company = context.company
    sensitivity = sensitivity if sensitivity is not None else {"rows": []}
    return {
        "ticker": company.ticker,
        "model_type": company.valuation_model,
        "status": "ok",
        "publishable": True,
        "current_price": context.current_price,
        "bear_value": scenario_values["bear"],
        "base_value": scenario_values["base"],
        "bull_value": scenario_values["bull"],
        "expected_value": expected,
        "margin_of_safety": margin_of_safety(expected, context.current_price),
        "missing_inputs": [],
        "reverse_dcf": {},
        "sensitivity": sensitivity,
        "moat": empty_moat_framework(
            company.company_type,
            company.factor_tags or [],
            company.special_risks or [],
        ),
        "trace": {
            "method": company.valuation_model,
            "engine": engine_key,
            "input_source": "financial_facts",
            "publishable": True,
            "status": "ok",
            "model_version": MODEL_VERSION,
            "scenario_style": f"{engine_key}_causal",
            "fact_ids": fact_ids,
            "periods": periods,
            "assumptions": assumptions,
            "probabilities": probabilities,
            "probability_method": "source_confidence_plus_company_quality",
        },
    }


class BankValuationEngine(ValuationEngine):
    """Bancos: P/B justificado sobre tangible book value.

    Supuestos: ``P/B = (ROE - g) / (CoE - g)`` acotado a [0.25, 3.0], con
    ``g`` = crecimiento del book (facts, o 0.0 por política explícita).
    Escenarios bear/base/bull: ROE ∓3pp/+2.5pp, CoE ±1.5pp/∓1pp, g ∓1pp/+0.5pp.
    Sensibilidad: tabla CoE (-100bp / base / +150bp) a ROE y g base.
    """

    key = "bank"

    def value(self, context: ValuationContext) -> dict:
        tangible_book = _latest(context, "tangible_book_value", "tangible_common_equity")
        shares = _latest(context, "shares_diluted")
        roe = _latest(context, "return_on_tangible_equity", "roe")
        cost_equity = _latest(context, "cost_of_equity")
        sourced = {
            "tangible_book_value": tangible_book,
            "shares_diluted": shares,
            "roe": roe,
            "cost_of_equity": cost_equity,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="Bank valuation requires sourced tangible book, diluted shares, ROTE/ROE and cost of equity.",
                snapshot=context.snapshot,
            )
        assert tangible_book and shares and roe and cost_equity
        growth = _latest(context, "book_value_growth", "tangible_book_growth")
        growth_value = growth.value if growth else 0.0
        if cost_equity.value <= growth_value or shares.value <= 0:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["cost_of_equity_above_book_value_growth"],
                reason="A justified price-to-book model requires cost of equity above sustainable growth.",
                snapshot=context.snapshot,
            )
        book_per_share = tangible_book.value / shares.value
        specs = {
            "bear": (roe.value - 0.03, cost_equity.value + 0.015, growth_value - 0.01),
            "base": (roe.value, cost_equity.value, growth_value),
            "bull": (roe.value + 0.025, max(cost_equity.value - 0.01, growth_value + 0.005), growth_value + 0.005),
        }
        values = {
            name: book_per_share * max(0.25, min(3.0, (scenario_roe - scenario_growth) / (scenario_cost - scenario_growth)))
            for name, (scenario_roe, scenario_cost, scenario_growth) in specs.items()
        }
        available = [value for value in sourced.values() if value is not None] + ([growth] if growth else [])
        probabilities = _probabilities(available, roe.value - cost_equity.value)
        sensitivity = _pb_sensitivity_rows(
            book_per_share=book_per_share,
            roe=roe.value,
            cost_of_equity=cost_equity.value,
            growth=growth_value,
        )
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={
                **{key: value.fact_id for key, value in sourced.items() if value},
                **({"book_value_growth": growth.fact_id} if growth else {}),
            },
            periods={
                **{key: value.period for key, value in sourced.items() if value},
                **({"book_value_growth": growth.period} if growth else {}),
            },
            assumptions={
                "book_per_share": book_per_share,
                "scenario_roe_cost_growth": specs,
                "growth_source": "financial_facts" if growth else "explicit_zero_growth_policy",
            },
            sensitivity=sensitivity,
        )


class InsurerValuationEngine(ValuationEngine):
    """Aseguradoras: P/B justificado ajustado por calidad de suscripción.

    Supuestos: ``valor = book/acc × P/B_justificado × factor_suscripción`` con
    ``factor = clamp(1 + (1 - combined_ratio) × 2, 0.75, 1.25)``; ``g`` de
    facts o 0.0 por política explícita. Escenarios: ROE ∓2.5pp/+2pp,
    CoE ±1.5pp/∓1pp, combined ratio ±3pp/∓2.5pp. Sensibilidad: tabla CoE a
    ROE, g y combined ratio base.
    """

    key = "insurer"

    def value(self, context: ValuationContext) -> dict:
        book = _latest(context, "book_value", "common_equity")
        shares = _latest(context, "shares_diluted")
        roe = _latest(context, "roe")
        cost_equity = _latest(context, "cost_of_equity")
        combined_ratio = _latest(context, "combined_ratio")
        sourced = {
            "book_value": book,
            "shares_diluted": shares,
            "roe": roe,
            "cost_of_equity": cost_equity,
            "combined_ratio": combined_ratio,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="Insurer valuation requires sourced book value, shares, ROE, cost of equity and combined ratio.",
                snapshot=context.snapshot,
            )
        assert book and shares and roe and cost_equity and combined_ratio
        growth = _latest(context, "book_value_growth")
        growth_value = growth.value if growth else 0.0
        if shares.value <= 0 or cost_equity.value <= growth_value:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["valid_shares_and_cost_of_equity_spread"],
                reason="Insurer price-to-book model inputs are economically inconsistent.",
                snapshot=context.snapshot,
            )
        book_per_share = book.value / shares.value
        specs = {
            "bear": (roe.value - 0.025, cost_equity.value + 0.015, combined_ratio.value + 0.03),
            "base": (roe.value, cost_equity.value, combined_ratio.value),
            "bull": (roe.value + 0.02, max(cost_equity.value - 0.01, growth_value + 0.005), combined_ratio.value - 0.025),
        }
        values = {}
        for name, (scenario_roe, scenario_cost, scenario_combined) in specs.items():
            justified_pb = (scenario_roe - growth_value) / (scenario_cost - growth_value)
            underwriting_quality = max(0.75, min(1.25, 1 + (1 - scenario_combined) * 2))
            values[name] = book_per_share * max(0.25, min(3.0, justified_pb)) * underwriting_quality
        available = list(sourced.values()) + ([growth] if growth else [])
        probabilities = _probabilities(available, 1 - combined_ratio.value)
        base_uw = max(0.75, min(1.25, 1 + (1 - combined_ratio.value) * 2))
        sensitivity = _pb_sensitivity_rows(
            book_per_share=book_per_share,
            roe=roe.value,
            cost_of_equity=cost_equity.value,
            growth=growth_value,
            underwriting_factor=base_uw,
        )
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={
                **{key: value.fact_id for key, value in sourced.items() if value},
                **({"book_value_growth": growth.fact_id} if growth else {}),
            },
            periods={
                **{key: value.period for key, value in sourced.items() if value},
                **({"book_value_growth": growth.period} if growth else {}),
            },
            assumptions={
                "book_per_share": book_per_share,
                "scenario_roe_cost_combined_ratio": specs,
                "growth_source": "financial_facts" if growth else "explicit_zero_growth_policy",
            },
            sensitivity=sensitivity,
        )


class ReitValuationEngine(ValuationEngine):
    """REITs: NAV directo por capitalización de NOI.

    Supuestos: ``valor/acc = max(0, NOI / cap_rate - net_debt) / acciones``
    con cap rate de mercado de facts (> 0). Escenarios: NOI ×(0.94/1.0/1.06),
    cap rate +75bp/base/−50bp (suelo 0.001). Sensibilidad: tabla cap rate
    (-50bp / base / +75bp) a NOI base.
    """

    key = "reit"

    def value(self, context: ValuationContext) -> dict:
        noi = _latest(context, "net_operating_income", "noi")
        cap_rate = _latest(context, "capitalization_rate", "cap_rate")
        net_debt = _latest(context, "net_debt")
        shares = _latest(context, "shares_diluted")
        sourced = {
            "net_operating_income": noi,
            "cap_rate": cap_rate,
            "net_debt": net_debt,
            "shares_diluted": shares,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="REIT NAV requires sourced NOI, cap rate, net debt and diluted shares.",
                snapshot=context.snapshot,
            )
        assert noi and cap_rate and net_debt and shares
        if cap_rate.value <= 0 or shares.value <= 0:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["positive_cap_rate_and_shares"],
                reason="REIT NAV inputs must be positive.",
                snapshot=context.snapshot,
            )
        specs = {
            "bear": (noi.value * 0.94, cap_rate.value + 0.0075),
            "base": (noi.value, cap_rate.value),
            "bull": (noi.value * 1.06, max(cap_rate.value - 0.005, 0.001)),
        }
        values = {
            name: max(0.0, scenario_noi / scenario_cap_rate - net_debt.value) / shares.value
            for name, (scenario_noi, scenario_cap_rate) in specs.items()
        }
        probabilities = _probabilities(list(sourced.values()), -cap_rate.value)
        sensitivity = _reit_sensitivity_rows(
            noi=noi.value,
            cap_rate=cap_rate.value,
            net_debt=net_debt.value,
            shares=shares.value,
        )
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={key: value.fact_id for key, value in sourced.items() if value},
            periods={key: value.period for key, value in sourced.items() if value},
            assumptions={"scenario_noi_cap_rate": specs, "net_debt": net_debt.value},
            sensitivity=sensitivity,
        )
