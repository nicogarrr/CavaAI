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
    ESEF_METRIC_MAP,
    SEC_INTANGIBLE_COMPONENTS,
    SEC_METRIC_MAP,
    SOURCE_PRIORITY,
    _collect_by_concept,
    _decimal,
    _merge_esef_periods,
    _merge_for_metric,
    _sum_disjoint_components,
    is_summed_component,
)


def _concepts(metric):
    for name, concepts, _unit in SEC_METRIC_MAP:
        if name == metric:
            return concepts
    raise AssertionError(f"{metric} is not in SEC_METRIC_MAP")


def _esef_concepts(metric):
    for name, concepts, _unit in ESEF_METRIC_MAP:
        if name == metric:
            return concepts
    raise AssertionError(f"{metric} is not in ESEF_METRIC_MAP")


# --------------------------------------------------------------------------
# disjoint components must be summed, not raced
# --------------------------------------------------------------------------


def test_intangibles_are_declared_as_summed_components():
    assert is_summed_component("intangible_assets") is True
    assert _concepts("intangible_assets") == SEC_INTANGIBLE_COMPONENTS


def test_a_metric_with_a_single_concept_is_not_summed():
    assert is_summed_component("goodwill") is False
    assert is_summed_component("total_assets") is False


def _us_gaap(**concepts):
    """A companyfacts-shaped fixture: {concept: {unit: [entry, ...]}}."""
    return {
        concept: {"units": {"USD": list(entries)}}
        for concept, entries in concepts.items()
    }


def _annual(end, value, filed, *, start=None, fp="FY", form="10-K"):
    entry = {"end": end, "val": value, "filed": filed, "fp": fp, "form": form}
    if start is not None:
        entry["start"] = start
    return entry


def test_sum_disjoint_components_adds_both_parts_of_the_same_period():
    merged = _sum_disjoint_components(
        {
            "FiniteLivedIntangibleAssetsNet": {
                "2024-12-31": {"end": "2024-12-31", "val": "5000", "filed": "2025-02-01"},
                "2023-12-31": {"end": "2023-12-31", "val": "4000", "filed": "2024-02-01"},
            },
            "IndefiniteLivedIntangibleAssetsExcludingGoodwill": {
                "2024-12-31": {"end": "2024-12-31", "val": "3000", "filed": "2025-02-01"},
                "2023-12-31": {"end": "2023-12-31", "val": "", "filed": "2024-02-01"},
            },
        }
    )
    assert merged["2024-12-31"]["val"] == pytest.approx(8000.0)
    # The year the second part was not reported keeps only what exists; an
    # empty value is not a zero to be added.
    assert merged["2023-12-31"]["val"] == pytest.approx(4000.0)
    assert merged["2024-12-31"]["_concept"] == (
        "FiniteLivedIntangibleAssetsNet+IndefiniteLivedIntangibleAssetsExcludingGoodwill"
    )
    assert merged["2023-12-31"]["_concept"] == "FiniteLivedIntangibleAssetsNet"


def test_sum_disjoint_components_keeps_the_breakdown_auditable():
    merged = _sum_disjoint_components(
        {
            "X": {"a": {"end": "a", "val": "10", "filed": "2025-01-01"}},
            "Y": {"a": {"end": "a", "val": "20", "filed": "2025-01-01"}},
        }
    )
    assert merged["a"]["val"] == pytest.approx(30.0)
    assert merged["a"]["_components"] == {"X": "10", "Y": "20"}


def test_the_ingestion_path_sums_both_intangible_components_of_a_period():
    """The contract has to hold on the path the refresh actually walks.

    The merge used to be fed a flat ``{end: entry}`` map that had already
    collapsed the two components into one winner, so the total stored whichever
    part was filed last and dropped the other. A unit test over a hand-built
    dict cannot catch that: the dict is the shape the code WISHED it had.
    """
    us_gaap = _us_gaap(
        FiniteLivedIntangibleAssetsNet=[
            _annual("2024-12-31", "5000", "2025-02-01"),
            _annual("2023-12-31", "4000", "2024-02-01"),
        ],
        IndefiniteLivedIntangibleAssetsExcludingGoodwill=[
            # Filed a month LATER, so a merge that raced the concepts kept this
            # one (3000) and lost the other (5000).
            _annual("2024-12-31", "3000", "2025-03-01"),
            _annual("2023-12-31", "2500", "2024-03-01"),
        ],
    )
    merged = _merge_for_metric(
        _collect_by_concept(
            us_gaap,
            SEC_INTANGIBLE_COMPONENTS,
            "USD",
            forms={"10-K", "20-F"},
            periods={"FY"},
            min_span=300,
            max_span=380,
        ),
        "intangible_assets",
    )
    assert merged["2024-12-31"]["val"] == pytest.approx(8000.0)
    assert merged["2023-12-31"]["val"] == pytest.approx(6500.0)


def test_alias_tags_are_still_merged_not_summed():
    """Revenue under two tags is one fact reported twice, not two facts."""
    us_gaap = _us_gaap(
        Revenues=[_annual("2024-12-31", "100", "2025-02-01")],
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            _annual("2024-12-31", "110", "2025-03-01"),
        ],
    )
    merged = _merge_for_metric(
        _collect_by_concept(
            us_gaap,
            ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
            "USD",
            forms={"10-K", "20-F"},
            periods={"FY"},
            min_span=None,
            max_span=None,
        ),
        "revenue",
    )
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(110.0)


def test_a_recast_inside_one_concept_wins_over_the_older_filing():
    us_gaap = _us_gaap(
        Revenues=[
            _annual("2024-12-31", "100", "2025-02-01"),
            _annual("2024-12-31", "105", "2026-02-01"),
        ]
    )
    merged = _merge_for_metric(
        _collect_by_concept(
            us_gaap,
            ["Revenues"],
            "USD",
            forms={"10-K", "20-F"},
            periods={"FY"},
            min_span=None,
            max_span=None,
        ),
        "revenue",
    )
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(105.0)


def test_a_quarterly_balance_instant_is_summed_too():
    """The 10-Q path had the same collapse, and instants skip duration filters."""
    us_gaap = _us_gaap(
        FiniteLivedIntangibleAssetsNet=[
            {"end": "2024-09-30", "val": "5000", "filed": "2024-11-01", "fp": "Q3", "form": "10-Q"}
        ],
        IndefiniteLivedIntangibleAssetsExcludingGoodwill=[
            {"end": "2024-09-30", "val": "3000", "filed": "2024-11-01", "fp": "Q3", "form": "10-Q"}
        ],
    )
    merged = _merge_for_metric(
        _collect_by_concept(
            us_gaap,
            SEC_INTANGIBLE_COMPONENTS,
            "USD",
            forms={"10-Q"},
            periods={"Q1", "Q2", "Q3", "Q4"},
            min_span=70,
            max_span=110,
        ),
        "intangible_assets",
    )
    assert merged["2024-09-30"]["val"] == pytest.approx(8000.0)
    # The label of the merged row still comes from a real filing.
    assert merged["2024-09-30"]["fp"] == "Q3"
    assert merged["2024-09-30"]["form"] == "10-Q"


def test_a_quarterly_flow_that_is_not_a_quarter_is_dropped():
    """Year-to-date and TTM variants must not land in a quarter row."""
    us_gaap = _us_gaap(
        Revenues=[
            _annual("2024-09-30", "300", "2024-11-01", start="2024-07-01", fp="Q3", form="10-Q"),
            _annual("2024-09-30", "750", "2024-11-01", start="2024-01-01", fp="Q3", form="10-Q"),
            _annual("2024-09-30", "1100", "2024-11-01", start="2023-10-01", fp="Q3", form="10-Q"),
        ]
    )
    merged = _merge_for_metric(
        _collect_by_concept(
            us_gaap,
            ["Revenues"],
            "USD",
            forms={"10-Q"},
            periods={"Q1", "Q2", "Q3", "Q4"},
            min_span=70,
            max_span=110,
        ),
        "revenue",
    )
    assert _decimal(merged["2024-09-30"]["val"]) == pytest.approx(300.0)


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
# ESEF: parts are summed, a disclosed total is not added to its own parts
# --------------------------------------------------------------------------


def _esef_capex(**values):
    facts = {}
    for concept, entries in values.items():
        facts[concept] = {"iso4217:EUR": entries}
    return facts


def _flow(end, start, value):
    return {"end": end, "start": start, "val": value}


def test_esef_capex_sums_the_parts_when_the_filer_disaggregates_it():
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [_flow("2024-12-31", "2024-01-01", "900")],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "100")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(1000.0)


def test_esef_capex_never_adds_a_disclosed_total_to_its_own_parts():
    """REP tags the combined concept; adding the parts to it triples the capex."""
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [_flow("2024-12-31", "2024-01-01", "900")],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "100")],
            concepts[2]: [_flow("2024-12-31", "2024-01-01", "950")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(950.0)


def test_esef_keeps_the_first_alias_and_never_sums_tags():
    concepts = _esef_concepts("total_equity")
    facts = _esef_capex(
        **{
            concepts[0]: [_flow("2024-12-31", "2024-01-01", "500")],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "480")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "total_equity")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(500.0)


def test_esef_skips_dimensional_and_non_annual_facts():
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [
                {**_flow("2024-12-31", "2024-01-01", "900"), "dims": {"1": "x"}},
                _flow("2024-12-31", "2024-10-01", "250"),
            ],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "100")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(100.0)


def test_esef_instant_facts_need_no_duration():
    concepts = _esef_concepts("total_equity")
    facts = _esef_capex(**{concepts[0]: [{"instant": "2024-12-31", "val": "700"}]})
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "total_equity")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(700.0)



def test_esef_capex_dedupes_the_same_fact_tagged_twice():
    # Two snapshots of one filing, or one snapshot read twice: the same tag,
    # the same context, the same value. It is ONE fact, and adding it twice
    # read 900+900+100 as the capex of the year.
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [
                _flow("2024-12-31", "2024-01-01", "900"),
                _flow("2024-12-31", "2024-01-01", "900"),
            ],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "100")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(1000.0)
    assert coverage["ambiguous"] == {}
    assert coverage["partial"] == {}


def test_esef_rejects_a_period_with_conflicting_facts_for_one_tag():
    # 900 and 950 for the same tag and period cannot both be the capex, and
    # without a filing date there is nothing honest to rank them with: the
    # period is refused, not averaged, summed or first-wins.
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [
                _flow("2024-12-31", "2024-01-01", "900"),
                _flow("2024-12-31", "2024-01-01", "950"),
            ],
            concepts[1]: [_flow("2024-12-31", "2024-01-01", "100")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert "2024-12-31" not in merged
    assert coverage["ambiguous"]["2024-12-31"] == {concepts[0]: ["900", "950"]}


def test_esef_a_disclosed_total_still_wins_over_ambiguous_parts():
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [
                _flow("2024-12-31", "2024-01-01", "900"),
                _flow("2024-12-31", "2024-01-01", "950"),
            ],
            concepts[2]: [_flow("2024-12-31", "2024-01-01", "1000")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(1000.0)


def test_esef_partial_coverage_is_explicit_and_not_published():
    # The filer reports both parts in 2023 but only PP&E in 2024: the 2024
    # subtotal is NOT the capex of the year, and publishing it as such inflates
    # the FCF. The period is left unpublished and the gap is stated.
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{
            concepts[0]: [
                _flow("2024-12-31", "2024-01-01", "900"),
                _flow("2023-12-31", "2023-01-01", "800"),
            ],
            concepts[1]: [_flow("2023-12-31", "2023-01-01", "100")],
        }
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert sorted(merged) == ["2023-12-31"]
    assert _decimal(merged["2023-12-31"]["val"]) == pytest.approx(900.0)
    assert coverage["partial"] == {"2024-12-31": [concepts[1]]}


def test_esef_a_part_the_filer_never_reports_is_not_partial():
    # Absence is only a gap when the filer reports the concept elsewhere. A
    # part that never appears can be zero or not applicable, and the sum of
    # what IS reported stands as the complete metric.
    concepts = _esef_concepts("capital_expenditure")
    facts = _esef_capex(
        **{concepts[0]: [_flow("2024-12-31", "2024-01-01", "900")]}
    )
    merged, coverage = _merge_esef_periods(facts, concepts, "iso4217:EUR", "capital_expenditure")
    assert _decimal(merged["2024-12-31"]["val"]) == pytest.approx(900.0)
    assert coverage["partial"] == {}

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
