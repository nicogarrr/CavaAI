from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, Document, SourceAudit, ThesisVersion
from app.services.source_auditor import SourceAuditor
from app.services.valuation_service import ValuationService


class ThesisService:
    def __init__(self) -> None:
        self.valuation_service = ValuationService()
        self.auditor = SourceAuditor()

    def latest(self, db: Session, ticker: str) -> ThesisVersion | None:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if not company:
            return None
        return db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )

    def generate(self, db: Session, ticker: str, force_new_version: bool = False) -> ThesisVersion:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if not company:
            raise ValueError(f"Unknown ticker: {ticker}")

        existing = self.latest(db, ticker)
        if existing and not force_new_version:
            return existing

        source = db.scalar(select(Document).where(Document.company_id == company.id).limit(1))
        valuation = self.valuation_service.value_company(db, company)
        self.valuation_service.persist_output(db, company, valuation)

        claims = [
            {
                "claim": f"{company.ticker} is tracked as {company.company_type}.",
                "source_id": source.id if source else None,
                "source_type": source.source_type if source else None,
                "confidence": 0.80,
                "material": True,
            },
            {
                "claim": f"Valuation method selected: {company.valuation_model}.",
                "source_id": source.id if source else None,
                "source_type": source.source_type if source else None,
                "confidence": 0.80,
                "material": True,
            },
        ]
        audit = self.auditor.audit(claims=claims, calculation_trace=valuation["trace"])

        previous = self.latest(db, ticker)
        version = (previous.version + 1) if previous else 1
        status = "final" if audit.passed else "draft_failed_audit"
        summary = (
            f"{company.ticker} is in the {company.company_type} bucket. "
            "This version is a grounded bootstrap thesis: it uses company master evidence and "
            "deterministic valuation traces until live SEC/FMP/IBKR ingestion is configured."
        )
        thesis_markdown = self._render_markdown(company, valuation, audit.as_dict())
        thesis = ThesisVersion(
            company_id=company.id,
            version=version,
            status=status,
            thesis_markdown=thesis_markdown,
            executive_summary=summary,
            rating=self._rating(valuation["margin_of_safety"], audit.passed),
            current_price=Decimal(str(valuation["current_price"])),
            bear_value=Decimal(str(valuation["bear_value"])),
            base_value=Decimal(str(valuation["base_value"])),
            bull_value=Decimal(str(valuation["bull_value"])),
            expected_value=Decimal(str(valuation["expected_value"])),
            margin_of_safety=Decimal(str(valuation["margin_of_safety"])),
            data_confidence_score=70 if source else 35,
            source_coverage_score=audit.source_coverage_score,
            red_team_score=65,
            valuation_risk_score=75 if "speculative" in company.factor_tags else 45,
        )
        db.add(thesis)
        db.flush()
        db.add(
            SourceAudit(
                thesis_version_id=thesis.id,
                passed=audit.passed,
                source_coverage_score=audit.source_coverage_score,
                unsupported_claims=audit.unsupported_claims,
                weak_claims=audit.weak_claims,
                data_conflicts=audit.data_conflicts,
                required_fixes=audit.required_fixes,
            )
        )
        db.commit()
        db.refresh(thesis)
        return thesis

    def _rating(self, margin_of_safety: float, audit_passed: bool) -> str:
        if not audit_passed:
            return "blocked"
        if margin_of_safety > 0.30:
            return "attractive"
        if margin_of_safety < -0.20:
            return "expensive"
        return "watch"

    def _render_markdown(self, company: Company, valuation: dict, audit: dict) -> str:
        return f"""# {company.ticker} Thesis v1

## 1. Executive Summary
{company.name} is tracked as `{company.company_type}` with model `{company.valuation_model}`.
This is a bootstrap thesis until live SEC/FMP/IBKR ingestion is configured.

## 2. One-Line Thesis
The investable question is whether the evidence supports the assumptions behind the selected model, not whether a model output looks attractive in isolation.

## 3. Business Model
Sector: {company.sector}. Industry: {company.industry}.

## 4. Latest Results
Blocked for final factual claims until SEC/FMP ingestion provides reported facts.

## 5. Historical Financials
Stored in `financial_facts` and `financial_statements` once ingested.

## 6. Free Cash Flow
Calculated by Python valuation modules from reported or approved assumptions.

## 7. Balance Sheet
Blocked for final claims until source reconciliation is present.

## 8. Capital Allocation
Tracked through filings, calls, buybacks, dilution and dividends.

## 9. Management And Calls
Call claims are stored separately and later verified against reported outcomes.

## 10. News And Catalysts
Material news updates require source audit and human approval before thesis versioning.

## 11. Risks
{", ".join(company.special_risks)}

## 12. Competition And Moat
Requires sourced evidence before final qualitative claims.

## 13. Valuation
- Current price: {valuation["current_price"]:.2f}
- Bear value: {valuation["bear_value"]:.2f}
- Base value: {valuation["base_value"]:.2f}
- Bull value: {valuation["bull_value"]:.2f}
- Expected value: {valuation["expected_value"]:.2f}
- Margin of safety: {valuation["margin_of_safety"]:.1%}

## 14. Reverse DCF
Required revenue growth: {valuation["reverse_dcf"]["required_revenue_growth"]:.1%}

## 15. Bear / Base / Bull
Scenario probabilities are stored in the calculation trace.

## 16. Red Team
Primary red-team question: what assumption would break first if the next filing contradicts the current model?

## 17. What Would Invalidate The Thesis
Unsupported claims, missing calculation traces, adverse primary filings or material assumption drift.

## 18. What To Watch
{", ".join(company.special_sources)}

## 19. Source Audit
Passed: {audit["passed"]}
Coverage score: {audit["source_coverage_score"]}
Unsupported claims: {audit["unsupported_claims"]}

## 20. Sources
Company master seed, then SEC/FMP/IR/FRED/GDELT documents as ingested.
"""

