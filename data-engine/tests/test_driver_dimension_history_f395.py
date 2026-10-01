"""F395: a unit change earlier in a driver's history must be reported."""

from decimal import Decimal

from app.models import FinancialFact
from app.services.driver_dimensions import DriverDimensionValidator


def _fact(metric, unit, year):
    return FinancialFact(
        company_id=1, metric=metric, value=Decimal("1"), unit=unit,
        period=f"FY{year}", fiscal_year=year, source_type="seed",
    )


def _validate(tpv_units):
    cache = {
        "tpv": [_fact("tpv", u, 2023 + i) for i, u in enumerate(tpv_units)],
        "take_rate": [_fact("take_rate", "decimal", 2025)],
    }
    return DriverDimensionValidator().validate("platform", cache)["errors"]


def test_unit_change_in_history_is_an_error_even_if_last_unit_is_valid():
    errs = _validate(["EUR", "USD"])
    hit = [e for e in errs if e.get("error") == "unit_changes_across_history"]
    assert hit and hit[0]["driver"] == "tpv"
    assert hit[0]["units"] == ["eur", "usd"]


def test_consistent_history_has_no_history_error():
    assert not [
        e for e in _validate(["USD", "USD"]) if e.get("error") == "unit_changes_across_history"
    ]
