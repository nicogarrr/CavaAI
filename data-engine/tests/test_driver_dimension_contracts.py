"""F404-F406: currency mixing, data scale and percent units must fail closed."""

from decimal import Decimal

from app.models import FinancialFact
from app.services.driver_dimensions import DriverDimensionValidator


def _fact(metric, unit, value=1):
    return FinancialFact(
        company_id=1, metric=metric, value=Decimal(str(value)), unit=unit,
        period="FY2025", fiscal_year=2025, source_type="seed",
    )


def _errors(formula, facts):
    cache = {f.metric: [f] for f in facts}
    return DriverDimensionValidator().validate(formula, cache)["errors"]


def test_mixed_currencies_are_rejected_without_fx():
    errs = _errors("space_defense", [
        _fact("price_per_launch", "USD/launch"),
        _fact("backlog", "EUR"),
        _fact("launches", "launches/year"),
        _fact("backlog_conversion", "decimal"),
    ])
    assert any(e.get("error") == "mixed_currencies_without_fx" for e in errs)


def test_single_currency_is_accepted():
    errs = _errors("space_defense", [
        _fact("price_per_launch", "EUR/launch"),
        _fact("backlog", "EUR"),
        _fact("launches", "launches/year"),
        _fact("backlog_conversion", "decimal"),
    ])
    assert not any(e.get("error") == "mixed_currencies_without_fx" for e in errs)


def test_gb_and_tb_are_not_collapsed():
    errs = _errors("space_network", [
        _fact("capacity_per_satellite", "TB/satellite/year"),
        _fact("price_per_gb", "USD/GB"),
    ])
    assert any(e.get("error") == "mixed_data_units_without_scale" for e in errs)


def test_percent_unit_requires_decimal_normalization():
    errs = _errors("platform", [_fact("tpv", "USD"), _fact("take_rate", "percent", 5)])
    assert any(e.get("error") == "percent_unit_requires_decimal_normalization" for e in errs)
    ok = _errors("platform", [_fact("tpv", "USD"), _fact("take_rate", "decimal", 0.05)])
    assert not any(e.get("error") for e in ok)
