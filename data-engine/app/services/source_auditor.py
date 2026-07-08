from dataclasses import dataclass, field


@dataclass
class AuditResult:
    passed: bool
    source_coverage_score: int
    unsupported_claims: list[str] = field(default_factory=list)
    weak_claims: list[str] = field(default_factory=list)
    data_conflicts: list[str] = field(default_factory=list)
    required_fixes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "source_coverage_score": self.source_coverage_score,
            "unsupported_claims": self.unsupported_claims,
            "weak_claims": self.weak_claims,
            "data_conflicts": self.data_conflicts,
            "required_fixes": self.required_fixes,
        }


class SourceAuditor:
    """Hard gate for material claims and valuation traces."""

    def audit(
        self,
        claims: list[dict],
        calculation_trace: dict | None,
        requires_sec_fmp_reconciliation: bool = False,
    ) -> AuditResult:
        unsupported = []
        weak = []
        conflicts = []
        fixes = []

        for claim in claims:
            text = claim.get("claim", "")
            if claim.get("material", True) and not claim.get("source_id"):
                unsupported.append(text)
            if claim.get("confidence", 1) < 0.65:
                weak.append(text)
            if claim.get("conflict"):
                conflicts.append(text)

        if calculation_trace is None or not calculation_trace:
            fixes.append("No calculation trace -> no valuation.")

        if requires_sec_fmp_reconciliation:
            sec_seen = any(claim.get("source_type") == "SEC" for claim in claims)
            fmp_seen = any(claim.get("source_type") == "FMP" for claim in claims)
            if not (sec_seen and fmp_seen):
                weak.append("SEC/FMP reconciliation missing for reported financial facts.")

        material_count = max(len([claim for claim in claims if claim.get("material", True)]), 1)
        covered_count = material_count - len(unsupported)
        source_coverage_score = max(0, round(100 * covered_count / material_count) - len(weak) * 5)
        passed = not unsupported and not conflicts and not fixes

        if unsupported:
            fixes.append("Add source_id to every material claim.")
        if conflicts:
            fixes.append("Resolve data conflicts before saving final thesis.")

        return AuditResult(
            passed=passed,
            source_coverage_score=source_coverage_score,
            unsupported_claims=unsupported,
            weak_claims=weak,
            data_conflicts=conflicts,
            required_fixes=fixes,
        )

