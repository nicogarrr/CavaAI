from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, Position, ValuationModel, ValuationOutput
from app.valuation import (
    DCFInputs,
    ReverseDCFInputs,
    Scenario,
    probability_weighted_value,
    run_dcf,
    sensitivity_grid,
    solve_required_growth,
)
from app.valuation.dilution_model import DilutionInput, run_dilution


def _position_price(db: Session, company_id: int) -> float:
    position = db.scalar(select(Position).where(Position.company_id == company_id).limit(1))
    return float(position.market_price) if position else 100.0


def _company_inputs(company: Company) -> dict:
    if "pre_fcf" in company.factor_tags or "speculative" in company.factor_tags:
        return {
            "revenue": 250.0,
            "growth": 0.28,
            "margin": 0.12,
            "wacc": 0.13,
            "terminal": 0.03,
            "net_debt": 50.0,
            "shares": 300.0,
        }
    if "commodities" in company.factor_tags:
        return {
            "revenue": 1200.0,
            "growth": 0.04,
            "margin": 0.18,
            "wacc": 0.10,
            "terminal": 0.02,
            "net_debt": 400.0,
            "shares": 450.0,
        }
    if "software" in company.factor_tags or "quality" in company.factor_tags:
        return {
            "revenue": 5000.0,
            "growth": 0.11,
            "margin": 0.28,
            "wacc": 0.09,
            "terminal": 0.03,
            "net_debt": -1000.0,
            "shares": 1000.0,
        }
    return {
        "revenue": 2000.0,
        "growth": 0.08,
        "margin": 0.18,
        "wacc": 0.10,
        "terminal": 0.025,
        "net_debt": 200.0,
        "shares": 500.0,
    }


class ValuationService:
    def value_company(self, db: Session, company: Company) -> dict:
        current_price = _position_price(db, company.id)
        inputs = _company_inputs(company)

        base_inputs = DCFInputs(
            revenue=inputs["revenue"],
            revenue_growth=inputs["growth"],
            fcf_margin=inputs["margin"],
            wacc=inputs["wacc"],
            terminal_growth=inputs["terminal"],
            net_debt=inputs["net_debt"],
            shares_outstanding=inputs["shares"],
        )
        base = run_dcf(base_inputs)
        bear = run_dcf(
            DCFInputs(
                **{
                    **base_inputs.__dict__,
                    "revenue_growth": max(inputs["growth"] - 0.08, -0.05),
                    "fcf_margin": max(inputs["margin"] - 0.06, 0.02),
                    "wacc": inputs["wacc"] + 0.02,
                }
            )
        )
        bull = run_dcf(
            DCFInputs(
                **{
                    **base_inputs.__dict__,
                    "revenue_growth": inputs["growth"] + 0.08,
                    "fcf_margin": min(inputs["margin"] + 0.06, 0.45),
                    "wacc": max(inputs["wacc"] - 0.01, inputs["terminal"] + 0.01),
                }
            )
        )

        weighted = probability_weighted_value(
            [
                Scenario("bear", 0.25, bear.value_per_share),
                Scenario("base", 0.50, base.value_per_share),
                Scenario("bull", 0.25, bull.value_per_share),
            ]
        )

        reverse = solve_required_growth(
            ReverseDCFInputs(
                market_price=current_price,
                revenue=inputs["revenue"],
                fcf_margin=inputs["margin"],
                wacc=inputs["wacc"],
                terminal_growth=inputs["terminal"],
                net_debt=inputs["net_debt"],
                shares_outstanding=inputs["shares"],
            )
        )

        sensitivity = sensitivity_grid(
            base_inputs,
            growth_values=[inputs["growth"] - 0.04, inputs["growth"], inputs["growth"] + 0.04],
            wacc_values=[inputs["wacc"] - 0.01, inputs["wacc"], inputs["wacc"] + 0.01],
        )

        trace = {
            "method": company.valuation_model,
            "bootstrap_notice": "Uses local bootstrap assumptions until SEC/FMP data is ingested.",
            "bear": bear.trace,
            "base": base.trace,
            "bull": bull.trace,
            "weighted": weighted["trace"],
            "reverse_dcf": reverse["trace"],
        }

        if "pre_fcf" in company.factor_tags or "speculative" in company.factor_tags:
            trace["dilution"] = run_dilution(
                DilutionInput(
                    current_shares=inputs["shares"],
                    new_capital_needed=100.0,
                    issuance_price=max(current_price * 0.85, 0.1),
                    current_value_per_share=base.value_per_share,
                )
            )

        return {
            "ticker": company.ticker,
            "model_type": company.valuation_model,
            "current_price": current_price,
            "bear_value": bear.value_per_share,
            "base_value": base.value_per_share,
            "bull_value": bull.value_per_share,
            "expected_value": weighted["expected_value"],
            "margin_of_safety": (weighted["expected_value"] / current_price - 1)
            if current_price
            else 0,
            "reverse_dcf": reverse,
            "sensitivity": sensitivity,
            "trace": trace,
        }

    def persist_output(self, db: Session, company: Company, valuation: dict) -> ValuationModel:
        latest = db.scalar(
            select(ValuationModel)
            .where(ValuationModel.company_id == company.id)
            .order_by(desc(ValuationModel.version))
            .limit(1)
        )
        version = (latest.version + 1) if latest else 1
        model = ValuationModel(
            company_id=company.id,
            model_type=valuation["model_type"],
            version=version,
            status="final",
            calculation_trace=valuation["trace"],
        )
        db.add(model)
        db.flush()

        for scenario, key in [("bear", "bear_value"), ("base", "base_value"), ("bull", "bull_value")]:
            db.add(
                ValuationOutput(
                    valuation_model_id=model.id,
                    scenario=scenario,
                    value_per_share=Decimal(str(valuation[key])),
                    output_payload=valuation,
                )
            )
        db.commit()
        db.refresh(model)
        return model

