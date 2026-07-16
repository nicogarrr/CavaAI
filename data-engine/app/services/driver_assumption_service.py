"""Editable, versioned operating-driver assumptions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, DriverAssumptionVersion, FundamentalDriver


class DriverAssumptionService:
    def list(
        self,
        db: Session,
        company: Company,
        *,
        driver_key: str | None = None,
        scenario: str | None = None,
    ) -> list[DriverAssumptionVersion]:
        statement = (
            select(DriverAssumptionVersion)
            .join(FundamentalDriver)
            .where(FundamentalDriver.company_id == company.id)
        )
        if driver_key:
            statement = statement.where(FundamentalDriver.driver_key == driver_key)
        if scenario:
            statement = statement.where(DriverAssumptionVersion.scenario == scenario)
        return list(
            db.scalars(
                statement.order_by(
                    DriverAssumptionVersion.fiscal_year,
                    DriverAssumptionVersion.scenario,
                    DriverAssumptionVersion.id,
                )
            ).all()
        )

    def create(
        self,
        db: Session,
        company: Company,
        *,
        driver_key: str,
        fiscal_year: int,
        scenario: str,
        value: Decimal,
        source: str,
        user_override: bool,
        confidence: Decimal,
        rationale: str,
        commit: bool = True,
    ) -> DriverAssumptionVersion:
        driver = db.scalar(
            select(FundamentalDriver)
            .where(
                FundamentalDriver.company_id == company.id,
                FundamentalDriver.driver_key == driver_key,
            )
            .order_by(desc(FundamentalDriver.created_at), desc(FundamentalDriver.id))
            .limit(1)
        )
        if driver is None:
            raise ValueError(
                f"Driver '{driver_key}' does not exist; build the company model first"
            )
        previous = db.scalar(
            select(DriverAssumptionVersion)
            .join(FundamentalDriver)
            .where(
                FundamentalDriver.company_id == company.id,
                FundamentalDriver.driver_key == driver_key,
                DriverAssumptionVersion.fiscal_year == fiscal_year,
                DriverAssumptionVersion.scenario == scenario,
            )
            .order_by(desc(DriverAssumptionVersion.id))
            .limit(1)
        )
        version = DriverAssumptionVersion(
            driver_id=driver.id,
            fiscal_year=fiscal_year,
            scenario=scenario,
            value=value,
            source=source,
            user_override=user_override,
            confidence=confidence,
            rationale=rationale,
            previous_version_id=previous.id if previous else None,
        )
        db.add(version)
        if commit:
            db.commit()
            db.refresh(version)
        else:
            db.flush()
        return version

    def active_overrides(
        self, db: Session, company: Company
    ) -> dict[str, dict[int, dict[str, dict[str, Any]]]]:
        rows = db.execute(
            select(DriverAssumptionVersion, FundamentalDriver.driver_key)
            .join(FundamentalDriver)
            .where(FundamentalDriver.company_id == company.id)
            .order_by(DriverAssumptionVersion.id)
        ).all()
        result: dict[str, dict[int, dict[str, dict[str, Any]]]] = {}
        for version, driver_key in rows:
            result.setdefault(driver_key, {}).setdefault(version.fiscal_year, {})[
                version.scenario
            ] = {
                "version_id": version.id,
                "previous_version_id": version.previous_version_id,
                "value": float(version.value),
                "source": version.source,
                "user_override": version.user_override,
                "confidence": float(version.confidence),
                "rationale": version.rationale,
            }
        return result


def driver_assumption_payload(
    version: DriverAssumptionVersion, *, driver_key: str | None = None
) -> dict[str, Any]:
    return {
        "id": version.id,
        "driver_id": version.driver_id,
        "driver_key": driver_key,
        "fiscal_year": version.fiscal_year,
        "scenario": version.scenario,
        "value": version.value,
        "source": version.source,
        "user_override": version.user_override,
        "confidence": version.confidence,
        "rationale": version.rationale,
        "previous_version_id": version.previous_version_id,
        "created_at": version.created_at,
    }
