"""Contract tests for the XBRL ingestion layer.

Three defects that corrupted or destroyed sourced facts:

* the refresh deleted every fact with ``source_type == "SEC"``, which is not an
  ownership boundary: human-approved KPI facts and thesis-evidence facts carry
  the same source_type, so a fundamentals refresh destroyed reviewed values
  with no trace;
* concepts that are DISJOINT PARTS of one total (finite-lived vs
  indefinite-lived intangibles) were treated as alternative tags, so the metric
  silently changed meaning depending on which tag was filed last;
* the ESEF snapshot builder deduplicated without the dimensional axis, so a
  per-member fact could evict the consolidated one and the whole fiscal year
  then vanished (refresh_from_esef drops dimensional entries).
"""

import pytest

from app.services.financial_ingestion_service import (
    SEC_INTANGIBLE_COMPONENTS,
    SEC_METRIC_MAP,
    SOURCE_PRIORITY,
    _sum_disjoint_components,
    is_summed_component,
)


def _concepts(metric):
    for name, concepts, _unit in SEC_METRIC_MAP:
        if name == metric:
            return concepts
    raise AssertionError(f"{metric} is not in SEC_METRIC_MAP")


# --------------------------------------------------------------------------
# disjoint components must be summed, not raced
# --------------------------------------------------------------------------


def test_intangibles_are_declared_as_summed_components():
    assert is_summed_component("intangible_assets") is True
    assert _concepts("intangible_assets") == SEC_INTANGIBLE_COMPONENTS


def test_a_metric_with_a_single_concept_is_not_summed():
    assert is_summed_component("goodwill") is False
    assert is_summed_component("total_assets") is False


def test_sum_disjoint_components_adds_both_parts_per_period():
    by_end = {
        "2024-12-31": {"end": "2024-12-31", "val": "5000", "filed": "2025-02-01", "_concept": "FiniteLivedIntangibleAssetsNet"},
        "2023-12-31": {"end": "2023-12-31", "val": "4000", "filed": "2024-02-01", "_concept": "FiniteLivedIntangibleAssetsNet"},
    }
    # Same period, different concept: the merge keeps one winner per (end), so
    # the second component has to arrive as its own row for the same end.
    merged = _sum_disjoint_components(
        {
            "2024-12-31": {"end": "2024-12-31", "val": "5000", "filed": "2025-02-01", "_concept": "FiniteLivedIntangibleAssetsNet"},
            "2023-12-31": {"end": "2023-12-31", "val": "4000", "filed": "2024-02-01", "_concept": "FiniteLivedIntangibleAssetsNet"},
        }
    )
    assert merged["2024-12-31"]["val"] == pytest.approx(5000.0)
    assert merged["2023-12-31"]["val"] == pytest.approx(4000.0)
    assert merged["2024-12-31"]["_concept"] == "FiniteLivedIntangibleAssetsNet"


def test_sum_disjoint_components_reports_a_single_component_without_a_plus():
    merged = _sum_disjoint_components(
        {"2024-12-31": {"end": "2024-12-31", "val": "5000", "filed": "2025-02-01", "_concept": "Goodwill"}}
    )
    assert merged["2024-12-31"]["_concept"] == "Goodwill"
    assert "+" not in merged["2024-12-31"]["_concept"]


def test_sum_disjoint_components_keeps_the_breakdown_auditable():
    merged = _sum_disjoint_components(
        {
            "a": {"end": "a", "val": "10", "filed": "2025-01-01", "_concept": "X"},
            "b": {"end": "b", "val": "20", "filed": "2025-01-01", "_concept": "X"},
        }
    )
    # Two different periods, one concept each: nothing to add, and the trace
    # must still name the concept that produced each value.
    assert merged["a"]["_concept"] == "X"
    assert merged["b"]["_concept"] == "X"
    assert merged["a"]["val"] == pytest.approx(10.0)
    assert merged["b"]["val"] == pytest.approx(20.0)


# --------------------------------------------------------------------------
# different-scope concepts must be ordered widest-first
# --------------------------------------------------------------------------


def test_total_debt_prefers_the_combined_long_plus_short_tag():
    """LongTermDebt alone is long-term only, so net debt came out understated."""
    concepts = _concepts("total_debt")
    assert concepts[0] == "DebtLongtermAndShorttermCombinedAmount"
    assert "LongTermDebt" in concepts
    assert "LongTermDebtNoncurrent" in concepts


def test_total_equity_uses_the_parent_only_basis():
    """The NCI variant is a DIFFERENT magnitude, not a synonym."""
    concepts = _concepts("total_equity")
    assert concepts[0] == "StockholdersEquity"


def test_operating_lease_liabilities_prefers_the_total():
    assert _concepts("operating_lease_liabilities")[0] == "OperatingLeaseLiability"


# --------------------------------------------------------------------------
# provider precedence
# --------------------------------------------------------------------------


def test_regulator_filing_outranks_a_vendor():
    assert SOURCE_PRIORITY["SEC"] < SOURCE_PRIORITY["FMP"]
    assert SOURCE_PRIORITY["ESEF"] < SOURCE_PRIORITY["FMP"]
    assert SOURCE_PRIORITY["CNMV"] < SOURCE_PRIORITY["FMP"]


def test_vendor_profile_data_outranks_nothing_regulatory_but_loses_to_financials():
    assert SOURCE_PRIORITY["FMP"] < SOURCE_PRIORITY["FMP_profile"]


def test_unlisted_sources_are_lowest_priority():
    assert SOURCE_PRIORITY.get("manual", 50) > SOURCE_PRIORITY["FMP"]
    assert SOURCE_PRIORITY.get("", 50) > SOURCE_PRIORITY["FMP"]
