"""Contract tests for the offline assurance gates.

Three of the gates used to return ``passed=True`` with a "no aplica" detail when
their key was absent. That made them skippable by omission: the gate whose job
is "the frozen valuation hash may not change" was silenced by not publishing the
hash, and it was exercised on 0 of 24 cases while CI stayed green.

The invented-numbers gate also only read ``claims``, never ``sections`` (the
prose the user actually reads), and matched numbers without binding them to a
metric, so ``frozen_facts={"employees": 391}`` validated the sentence
"Revenue was 391 MUSD".
"""

from evals.gates import (
    _norm_number,
    gate_material_claims_have_evidence,
    gate_no_invented_numbers,
    gate_probabilities_sum_to_one,
    gate_replay_no_duplicate_version,
    gate_valuation_unchanged_by_prompt_edits,
)


def _case(artifact=None, expected=None, frozen=None):
    return {
        "artifact": artifact or {},
        "expected": expected or {},
        "frozen_facts": frozen or {},
    }


# --------------------------------------------------------------------------
# a missing key must fail, not skip
# --------------------------------------------------------------------------


def test_probabilities_gate_fails_when_the_key_is_missing():
    result = gate_probabilities_sum_to_one(_case())
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_probabilities_gate_fails_when_they_do_not_sum_to_one():
    result = gate_probabilities_sum_to_one(
        _case({"scenario_probabilities": {"bear": 0.4, "base": 0.4, "bull": 0.4}})
    )
    assert result["passed"] is False


def test_valuation_hash_gate_fails_when_the_hash_is_missing():
    result = gate_valuation_unchanged_by_prompt_edits(_case())
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_valuation_hash_gate_fails_when_it_moved():
    result = gate_valuation_unchanged_by_prompt_edits(
        _case({"valuation_hash": "b"}, {"valuation_hash": "a"})
    )
    assert result["passed"] is False


def test_valuation_hash_gate_passes_when_it_matches():
    result = gate_valuation_unchanged_by_prompt_edits(
        _case({"valuation_hash": "a"}, {"valuation_hash": "a"})
    )
    assert result["passed"] is True


def test_replay_gate_fails_when_versions_are_missing():
    result = gate_replay_no_duplicate_version(_case())
    assert result["passed"] is False


def test_replay_gate_fails_on_duplicates():
    result = gate_replay_no_duplicate_version(_case({"versions": [1, 1, 2]}))
    assert result["passed"] is False


# --------------------------------------------------------------------------
# invented numbers: sections included, metric-bound
# --------------------------------------------------------------------------


def test_invented_number_in_a_claim_is_caught():
    result = gate_no_invented_numbers(
        _case(
            {"claims": [{"text": "Revenue was 999 MUSD", "metric": "revenue_musd"}]},
            frozen={"revenue_musd": 391},
        )
    )
    assert result["passed"] is False
    assert "revenue_musd" in result["details"][0]


def test_invented_number_in_a_section_is_caught():
    """The section prose is what the user reads; it was never checked."""
    result = gate_no_invented_numbers(
        _case(
            {"sections": [{"key": "valuation", "content": "Implied value 999 MUSD"}]},
            frozen={"revenue_musd": 391},
        )
    )
    assert result["passed"] is False


def test_a_number_is_not_vouched_for_by_another_metric():
    """A headcount must not validate a revenue sentence."""
    result = gate_no_invented_numbers(
        _case(
            {"claims": [{"text": "Revenue was 391 MUSD", "metric": "revenue_musd"}]},
            frozen={"employees": 391},
        )
    )
    assert result["passed"] is False
    assert "revenue_musd" in result["details"][0]


def test_a_matching_number_for_its_own_metric_passes():
    result = gate_no_invented_numbers(
        _case(
            {"claims": [{"text": "Revenue was 391 MUSD", "metric": "revenue_musd"}]},
            frozen={"revenue_musd": 391},
        )
    )
    assert result["passed"] is True


def test_sourced_number_in_a_section_passes():
    result = gate_no_invented_numbers(
        _case(
            {"sections": [{"key": "valuation", "content": "Revenue 391 MUSD"}]},
            frozen={"revenue_musd": 391},
        )
    )
    assert result["passed"] is True


# --------------------------------------------------------------------------
# normalisation must not manufacture a passing number
# --------------------------------------------------------------------------


def test_decimal_comma_is_not_stripped_as_a_thousands_separator():
    """'1,2' is 1.2; stripping the comma turned a small figure into 12.0."""
    assert _norm_number("1,2") == 1.2
    assert _norm_number("1.234,56") == 1234.56


def test_thousands_separator_is_still_handled():
    assert _norm_number("1,234") == 1234.0
    assert _norm_number("391") == 391.0


def test_a_hallucinated_magnitude_does_not_pass_through_normalisation():
    result = gate_no_invented_numbers(
        _case(
            {"claims": [{"text": "Ingresos de 1,2 MUSD", "metric": "revenue_musd"}]},
            frozen={"revenue_musd": 12},
        )
    )
    assert result["passed"] is False


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------


def test_unsourced_material_claim_fails():
    result = gate_material_claims_have_evidence(
        _case({"claims": [{"text": "c", "evidence_ids": []}], "evidence": [{"id": "e1"}]})
    )
    assert result["passed"] is False


def test_section_citing_unknown_evidence_fails():
    result = gate_material_claims_have_evidence(
        _case(
            {
                "claims": [],
                "sections": [{"key": "facts", "content": "x", "citations": ["nope"]}],
                "evidence": [{"id": "e1"}],
            }
        )
    )
    assert result["passed"] is False


def test_section_citing_known_evidence_passes():
    result = gate_material_claims_have_evidence(
        _case(
            {
                "claims": [],
                "sections": [{"key": "facts", "content": "x", "citations": ["e1"]}],
                "evidence": [{"id": "e1"}],
            }
        )
    )
    assert result["passed"] is True
