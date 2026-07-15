from __future__ import annotations

import hashlib
import json
from copy import deepcopy
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
    FundamentalValuationSnapshot,
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

    @staticmethod
    def _hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def fingerprints(self, payload: dict[str, Any]) -> dict[str, str]:
        market_opportunity = deepcopy(payload.get("market_opportunity") or {})
        market_opportunity.pop("implied_by_valuation", None)
        market_opportunity.pop("market_share", None)
        inputs = {
            "algorithm_version": payload.get("algorithm_version") or payload.get("model_version"),
            "code_commit_sha": payload.get("code_commit_sha"),
            "framework": payload.get("framework"),
            "horizon_years": payload.get("horizon_years"),
            "historical_review": payload.get("historical_review"),
            "assumptions": payload.get("assumptions"),
            "driver_model": payload.get("driver_model"),
            "market_opportunity": market_opportunity,
            "scenario_configuration": payload.get("scenario_configuration"),
            "funding_policy": payload.get("funding_policy"),
        }
        forecast = {
            scenario: {
                "probability": value.get("probability"),
                "assumptions": value.get("assumptions"),
                "forecast": value.get("forecast"),
            }
            for scenario, value in (payload.get("scenarios") or {}).items()
        }
        market_snapshot = {
            "current_price": payload.get("current_price"),
            "market_as_of": (payload.get("trace") or {}).get("market_as_of"),
        }
        valuation_snapshot = {
            "reverse_dcf": payload.get("reverse_dcf"),
            "scenario_valuations": {
                scenario: value.get("valuation")
                for scenario, value in (payload.get("scenarios") or {}).items()
            },
            "implied_market_opportunity": (
                (payload.get("market_opportunity") or {}).get("implied_by_valuation")
            ),
        }
        return {
            "input": self._hash(inputs),
            "forecast": self._hash(forecast),
            "market": self._hash(market_snapshot),
            "valuation": self._hash(valuation_snapshot),
        }

    def fingerprint(self, payload: dict[str, Any]) -> str:
        return self.fingerprints(payload)["input"]

    def persist(
        self,
        db: Session,
        company: Company,
        payload: dict[str, Any],
        *,
        commit: bool = True,
    ) -> FundamentalModelVersion | None:
        tenant_id = db.info.get("tenant_id")
        if tenant_id is None:
            return None

        fingerprints = self.fingerprints(payload)
        fingerprint = fingerprints["input"]
        existing = db.scalar(
            select(FundamentalModelVersion).where(
                FundamentalModelVersion.company_id == company.id,
                FundamentalModelVersion.input_fingerprint == fingerprint,
            )
        )
        if existing:
            model = existing
            model.market_snapshot_fingerprint = fingerprints["market"]
            model.valuation_snapshot_fingerprint = fingerprints["valuation"]
        else:
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
                algorithm_version=str(
                    payload.get("algorithm_version") or payload.get("model_version") or "unknown"
                ),
                framework_key=str((payload.get("framework") or {}).get("key") or "unknown"),
                horizon_years=int(payload.get("horizon_years") or 5),
                status=str(payload.get("status") or "unknown"),
                publishable=bool(payload.get("publishable")),
                input_fingerprint=fingerprint,
                forecast_fingerprint=fingerprints["forecast"],
                market_snapshot_fingerprint=fingerprints["market"],
                valuation_snapshot_fingerprint=fingerprints["valuation"],
                code_commit_sha=str(payload.get("code_commit_sha") or "unknown")[:80],
                scenario_probabilities=probabilities,
                model_snapshot=self._operating_snapshot(payload),
            )
            db.add(model)
            db.flush()
            self._persist_drivers(db, company, model, payload)
            self._persist_assumptions(db, company, model, payload)
            self._persist_forecasts(db, company, model, payload)
        self._persist_valuation_snapshot(db, company, model, payload, fingerprints)
        if commit:
            db.commit()
            db.refresh(model)
        else:
            db.flush()
        return model

    def latest_payload(self, db: Session, company: Company) -> dict[str, Any] | None:
        model = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        if model is None:
            return None
        valuation = db.scalar(
            select(FundamentalValuationSnapshot)
            .where(FundamentalValuationSnapshot.model_version_id == model.id)
            .order_by(desc(FundamentalValuationSnapshot.created_at), desc(FundamentalValuationSnapshot.id))
            .limit(1)
        )
        payload = self._compose(model.model_snapshot, valuation.snapshot if valuation else None)
        payload["persistence"] = {
            "model_version_id": model.id,
            "version": model.version,
            "input_fingerprint": model.input_fingerprint,
            "forecast_fingerprint": model.forecast_fingerprint,
            "market_snapshot_fingerprint": model.market_snapshot_fingerprint,
            "valuation_snapshot_fingerprint": model.valuation_snapshot_fingerprint,
            "code_commit_sha": model.code_commit_sha,
            "status": "persisted",
        }
        return payload

    def _persist_valuation_snapshot(
        self,
        db: Session,
        company: Company,
        model: FundamentalModelVersion,
        payload: dict[str, Any],
        fingerprints: dict[str, str],
    ) -> FundamentalValuationSnapshot:
        row = db.scalar(
            select(FundamentalValuationSnapshot).where(
                FundamentalValuationSnapshot.model_version_id == model.id,
                FundamentalValuationSnapshot.market_snapshot_fingerprint == fingerprints["market"],
            )
        )
        if row is None:
            row = FundamentalValuationSnapshot(
                model_version_id=model.id,
                company_id=company.id,
                current_price=_decimal(payload.get("current_price")),
                market_snapshot_fingerprint=fingerprints["market"],
                valuation_snapshot_fingerprint=fingerprints["valuation"],
                snapshot=self._valuation_snapshot(payload),
            )
            db.add(row)
        else:
            row.valuation_snapshot_fingerprint = fingerprints["valuation"]
            row.snapshot = self._valuation_snapshot(payload)
        db.flush()
        return row

    @staticmethod
    def _operating_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        result.pop("current_price", None)
        result.pop("reverse_dcf", None)
        result.pop("persistence", None)
        for scenario in (result.get("scenarios") or {}).values():
            scenario.pop("valuation", None)
        opportunity = result.get("market_opportunity") or {}
        opportunity.pop("implied_by_valuation", None)
        return result

    @staticmethod
    def _valuation_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "current_price": payload.get("current_price"),
            "reverse_dcf": payload.get("reverse_dcf"),
            "scenario_valuations": {
                scenario: value.get("valuation")
                for scenario, value in (payload.get("scenarios") or {}).items()
            },
            "implied_by_valuation": (
                (payload.get("market_opportunity") or {}).get("implied_by_valuation")
            ),
        }

    @staticmethod
    def _compose(operating: dict[str, Any], valuation: dict[str, Any] | None) -> dict[str, Any]:
        result = deepcopy(operating)
        if not valuation:
            return result
        result["current_price"] = valuation.get("current_price")
        result["reverse_dcf"] = valuation.get("reverse_dcf") or {}
        for scenario, value in (valuation.get("scenario_valuations") or {}).items():
            if scenario in (result.get("scenarios") or {}):
                result["scenarios"][scenario]["valuation"] = value
        if valuation.get("implied_by_valuation") is not None:
            result.setdefault("market_opportunity", {})["implied_by_valuation"] = valuation[
                "implied_by_valuation"
            ]
        return result

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
