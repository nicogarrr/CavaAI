"""SourceAuditor contract tests.

The auditor is the hard gate between evidence and publication: material
claims without sources, data conflicts, and missing calculation traces
must block, while weak-but-sourced claims only erode the coverage score.
"""

from app.services.source_auditor import SourceAuditor


def _claim(**overrides):
    base = {
        "claim": "Revenue grows 10 percent",
        "material": True,
        "source_id": 42,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_clean_claims_with_trace_pass_at_full_coverage():
    result = SourceAuditor().audit([_claim()], {"engine": "dcf"})
    assert result.passed is True
    assert result.source_coverage_score == 100
    assert result.required_fixes == []
    assert result.as_dict()["passed"] is True


def test_material_claim_without_source_blocks():
    result = SourceAuditor().audit([_claim(source_id=None)], {"engine": "dcf"})
    assert result.passed is False
    assert result.unsupported_claims == ["Revenue grows 10 percent"]
    assert result.source_coverage_score == 0
    assert "Add source_id to every material claim." in result.required_fixes


def test_non_material_claim_without_source_does_not_block():
    result = SourceAuditor().audit(
        [_claim(material=False, source_id=None)], {"engine": "dcf"}
    )
    assert result.passed is True
    assert result.unsupported_claims == []
    # Non-material claims are excluded from the coverage denominator.
    assert result.source_coverage_score == 100


def test_low_confidence_erodes_score_but_does_not_block():
    claims = [_claim(confidence=0.4), _claim(claim="Second", confidence=0.5)]
    result = SourceAuditor().audit(claims, {"engine": "dcf"})
    assert result.passed is True
    assert result.weak_claims == ["Revenue grows 10 percent", "Second"]
    assert result.source_coverage_score == 100 - 2 * 5


def test_conflicts_block_and_require_resolution():
    result = SourceAuditor().audit([_claim(conflict=True)], {"engine": "dcf"})
    assert result.passed is False
    assert result.data_conflicts == ["Revenue grows 10 percent"]
    assert "Resolve data conflicts before saving final thesis." in result.required_fixes


def test_missing_trace_blocks_even_with_clean_claims():
    result = SourceAuditor().audit([_claim()], None)
    assert result.passed is False
    assert "No calculation trace -> no valuation." in result.required_fixes


def test_sec_fmp_reconciliation_flagged_when_one_side_missing():
    claims = [_claim(source_type="SEC")]
    result = SourceAuditor().audit(
        claims, {"engine": "dcf"}, requires_sec_fmp_reconciliation=True
    )
    assert any("SEC/FMP reconciliation missing" in item for item in result.weak_claims)
    both = SourceAuditor().audit(
        [_claim(source_type="SEC"), _claim(claim="F", source_type="FMP")],
        {"engine": "dcf"},
        requires_sec_fmp_reconciliation=True,
    )
    assert not any("SEC/FMP" in item for item in both.weak_claims)


def test_score_never_drops_below_zero():
    claims = [_claim(claim=f"c{i}", confidence=0.1) for i in range(30)]
    result = SourceAuditor().audit(claims, {"engine": "dcf"})
    assert result.source_coverage_score == 0
