from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    FundamentalAssumption,
    FundamentalDriver,
    FundamentalForecast,
    FundamentalModelVersion,
)


FORECAST_METRICS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "ebitda",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "working_capital",
    "net_debt",
    "shares_diluted",
    "fcf_per_share",
    "fcf_margin",
    "roic",
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class FundamentalModelRepository:
    """Versioned PostgreSQL persistence for reproducible fundamental models."""

    def fingerprint(self, payload: dict[str, Any]) -> str:
        inputs = {
            "engine_version": payload.get("model_version"),
            "framework": payload.get("framework"),
            "horizon_years": payload.get("horizon_years"),
            "historical_review": payload.get("historical_review"),
            "assumptions": payload.get("assumptions"),
            "driver_model": payload.get("driver_model"),
            "market_opportunity": payload.get("market_opportunity"),
        }
        encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def persist(
        self,
        db: Session,
        company: Company,
        payload: dict[str, Any],
    ) -> FundamentalModelVersion | None:
        tenant_id = db.info.get("tenant_id")
        if tenant_id is None:
            return None

        fingerprint = self.fingerprint(payload)
        existing = db.scalar(
            select(FundamentalModelVersion).where(
                FundamentalModelVersion.company_id == company.id,
                FundamentalModelVersion.input_fingerprint == fingerprint,
            )
        )
        if existing:
            return existing

        previous = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        probabilities = {
            name: scenario.get("probability")
            for name, scenario in (payload.get("scenarios") or {}).items()
        }
        model = FundamentalModelVersion(
            company_id=company.id,
            version=(previous.version + 1) if previous else 1,
            engine_version=str(payload.get("model_version") or "unknown"),
            framework_key=str((payload.get("framework") or {}).get("key") or "unknown"),
            horizon_years=int(payload.get("horizon_years") or 5),
            status=str(payload.get("status") or "unknown"),
            publishable=bool(payload.get("publishable")),
            input_fingerprint=fingerprint,
            scenario_probabilities=probabilities,
            model_snapshot=payload,
        )
        db.add(model)
        db.flush()

        self._persist_drivers(db, company, model, payload)
        self._persist_assumptions(db, company, model, payload)
        self._persist_forecasts(db, company, model, payload)
        db.commit()
        db.refresh(model)
        return model

    def _persist_drivers(self, db, company, model, payload) -> None:
        for driver in payload.get("driver_model") or []:
            db.add(
                FundamentalDriver(
                    model_version_id=model.id,
                    company_id=company.id,
                    driver_key=driver["key"],
                    driver_type=driver["driver_type"],
                    required=bool(driver["required"]),
                    status=driver["status"],
                    value=_decimal(driver.get("value")),
                    unit=driver.get("unit") or "unknown",
                    confidence=_decimal(driver.get("confidence")) or Decimal("0"),
                    source_fact_ids=driver.get("source_fact_ids") or [],
                    trace=driver.get("trace") or {},
                )
            )

    def _persist_assumptions(self, db, company, model, payload) -> None:
        for key, assumption in (payload.get("assumptions") or {}).items():
            db.add(self._assumption(company, model, key, "model", assumption))
        for scenario, scenario_payload in (payload.get("scenarios") or {}).items():
            for key, assumption in (scenario_payload.get("assumptions") or {}).items():
                db.add(self._assumption(company, model, key, scenario, assumption))

    def _assumption(self, company, model, key, scenario, assumption):
        return FundamentalAssumption(
            model_version_id=model.id,
            company_id=company.id,
            assumption_key=key,
            scenario=scenario,
            value=_decimal(assumption.get("value")),
            unit=assumption.get("unit") or "decimal",
            source_type=assumption.get("source_type") or "unknown",
            basis=assumption.get("basis") or "",
            confidence=_decimal(assumption.get("confidence")) or Decimal("0"),
            source_fact_ids=assumption.get("source_fact_ids") or [],
        )

    def _persist_forecasts(self, db, company, model, payload) -> None:
        for scenario, scenario_payload in (payload.get("scenarios") or {}).items():
            probability = _decimal(scenario_payload.get("probability")) or Decimal("0")
            for point in scenario_payload.get("forecast") or []:
                for metric in FORECAST_METRICS:
                    value = point.get(metric)
                    if value is None:
                        continue
                    evidence = (point.get("evidence") or {}).get(metric) or {}
                    unit = "decimal" if metric.endswith("margin") or metric == "roic" else (
                        "shares" if metric == "shares_diluted" else "USD"
                    )
                    db.add(
                        FundamentalForecast(
                            model_version_id=model.id,
                            company_id=company.id,
                            scenario=scenario,
                            probability=probability,
                            fiscal_year=int(point["year"]),
                            metric=metric,
                            value=_decimal(value),
                            unit=unit,
                            source_fact_ids=evidence.get("source_fact_ids") or [],
                            trace={
                                "calculation": evidence.get("calculation"),
                                "wacc": point.get("wacc"),
                            },
                        )
                    )
