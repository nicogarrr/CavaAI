"""Thesis generation with evidence fingerprinting and honest insufficient-data handling."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    FinancialFact,
    MarketPrice,
    SourceAudit,
    ThesisVersion,
)
from app.services.source_auditor import SourceAuditor
from app.services.source_hierarchy_service import classify_source
from app.services.long_term_model_service import LongTermModelService
from app.services.valuation_service import ValuationService
from app.valuation.engines.base import MODEL_VERSION
from app.valuation.financial_snapshot import FinancialSnapshotBuilder
from app.valuation.moat_framework import empty_moat_framework

PROMPT_VERSION = "thesis-render-v2"


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

    def _input_fingerprint(
        self,
        db: Session,
        company: Company,
        valuation: dict,
        long_term_model: dict,
    ) -> str:
        documents = list(
            db.scalars(select(Document).where(Document.company_id == company.id).order_by(Document.id)).all()
        )
        facts = list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id)
                .order_by(FinancialFact.id)
            ).all()
        )
        market_price = db.scalar(
            select(MarketPrice)
            .where(MarketPrice.company_id == company.id)
            .order_by(desc(MarketPrice.date))
            .limit(1)
        )
        payload = {
            "documents": [f"{d.id}:{d.checksum or d.updated_at.isoformat()}" for d in documents],
            "facts": [f"{f.id}:{f.metric}:{f.period}:{f.value}" for f in facts],
            "market_price": (
                f"{market_price.date.isoformat()}:{market_price.close}" if market_price else None
            ),
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
            "valuation_status": valuation.get("status"),
            "engine": (valuation.get("trace") or {}).get("engine"),
            "input_source": (valuation.get("trace") or {}).get("input_source"),
            "fundamental_model_fingerprint": (
                long_term_model.get("persistence") or {}
            ).get("input_fingerprint"),
            "fundamental_model_status": long_term_model.get("status"),
            "missing_mandatory_drivers": long_term_model.get(
                "missing_mandatory_drivers"
            ),
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate(self, db: Session, ticker: str, force_new_version: bool = False) -> ThesisVersion:
        """Persist model, valuation, thesis, evidence, graph and red team atomically."""
        try:
            return self._generate_atomic(db, ticker, force_new_version)
        except Exception:
            db.rollback()
            raise

    def _generate_atomic(
        self, db: Session, ticker: str, force_new_version: bool = False
    ) -> ThesisVersion:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if not company:
            raise ValueError(f"Unknown ticker: {ticker}")

        long_term_model = LongTermModelService().build(
            db, company, horizon=5, commit=False
        )
        valuation = self.valuation_service.value_company(db, company)
        missing_drivers = long_term_model.get("missing_mandatory_drivers") or []
        if missing_drivers:
            valuation["publishable"] = False
            valuation["missing_inputs"] = sorted(
                set((valuation.get("missing_inputs") or []) + missing_drivers)
            )
        valuation.setdefault("trace", {})["fundamental_model"] = {
            "model_version_id": (long_term_model.get("persistence") or {}).get(
                "model_version_id"
            ),
            "version": (long_term_model.get("persistence") or {}).get("version"),
            "framework": (long_term_model.get("framework") or {}).get("key"),
            "status": long_term_model.get("status"),
            "publishable": long_term_model.get("publishable"),
            "missing_mandatory_drivers": missing_drivers,
        }
        valuation["long_term_model"] = long_term_model
        fingerprint = self._input_fingerprint(db, company, valuation, long_term_model)

        existing = self.latest(db, ticker)
        if existing and not force_new_version:
            if getattr(existing, "input_fingerprint", None) == fingerprint:
                db.rollback()
                return existing
            # Material evidence changed — fall through and create a new version.

        self.valuation_service.persist_output(db, company, valuation, commit=False)
        snapshot = FinancialSnapshotBuilder().build(db, company)
        facts = snapshot.facts

        claims = self._build_claims(company, facts, valuation)
        audit = self.auditor.audit(
            claims=claims,
            calculation_trace=valuation.get("trace"),
            requires_sec_fmp_reconciliation=(valuation.get("trace") or {}).get("input_source")
            == "financial_facts",
        )

        previous = self.latest(db, ticker)
        version = (previous.version + 1) if previous else 1

        publishable = bool(valuation.get("publishable"))
        if valuation.get("status") == "insufficient_data":
            status = "insufficient_data"
        elif not audit.passed:
            status = "draft_failed_audit"
        elif publishable:
            status = "final"
        else:
            status = "draft"

        summary = self._executive_summary(company, valuation)
        thesis_markdown = self._render_markdown(
            company,
            valuation,
            audit.as_dict(),
            facts,
            long_term_model=long_term_model,
            version=version,
        )

        def _dec(value) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        thesis = ThesisVersion(
            company_id=company.id,
            version=version,
            status=status,
            thesis_markdown=thesis_markdown,
            executive_summary=summary,
            rating=self._rating(
                valuation.get("margin_of_safety"),
                audit.passed,
                valuation.get("status"),
            ),
            current_price=_dec(valuation.get("current_price")),
            bear_value=_dec(valuation.get("bear_value")),
            base_value=_dec(valuation.get("base_value")),
            bull_value=_dec(valuation.get("bull_value")),
            expected_value=_dec(valuation.get("expected_value")),
            margin_of_safety=_dec(valuation.get("margin_of_safety")),
            data_confidence_score=self._confidence_score(valuation, facts),
            source_coverage_score=audit.source_coverage_score,
            red_team_score=0,
            valuation_risk_score=75 if "speculative" in (company.factor_tags or []) else 45,
            input_fingerprint=fingerprint,
        )
        db.add(thesis)
        db.flush()
        self._persist_claims(db, company, thesis, claims)
        db.add(
            SourceAudit(
                thesis_version_id=thesis.id,
                passed=audit.passed and publishable,
                source_coverage_score=audit.source_coverage_score,
                unsupported_claims=audit.unsupported_claims,
                weak_claims=audit.weak_claims,
                data_conflicts=audit.data_conflicts,
                required_fixes=audit.required_fixes
                + (
                    [f"Missing valuation inputs: {', '.join(valuation.get('missing_inputs') or [])}"]
                    if valuation.get("missing_inputs")
                    else []
                ),
            )
        )
        db.flush()
        from app.services.red_team_service import RedTeamService
        from app.services.thesis_graph_service import ThesisGraphService

        ThesisGraphService().build(db, company, thesis, commit=False)
        RedTeamService().run(db, company, thesis, commit=False)
        db.commit()
        db.refresh(thesis)
        return thesis

    def _persist_claims(
        self,
        db: Session,
        company: Company,
        thesis: ThesisVersion,
        claims: list[dict],
    ) -> None:
        for payload in claims:
            if not payload.get("material", True):
                continue
            statement = str(payload.get("claim") or "").strip()
            if not statement:
                continue
            source_id = payload.get("source_id")
            source_type = str(payload.get("source_type") or "unknown")
            claim = Claim(
                company_id=company.id,
                thesis_version_id=thesis.id,
                statement=statement,
                claim_type=str(payload.get("predicate") or "generated_thesis"),
                status="supported" if source_id else "unverified",
                confidence=Decimal(str(payload.get("confidence", 0.5))),
                materiality_score=8,
                source_quality=classify_source(source_type).key,
                created_by="thesis_generation",
                metadata_={
                    "generated_claim_id": payload.get("claim_id"),
                    "verification_state": payload.get(
                        "verification_state", "unverified"
                    ),
                    "prompt_version": PROMPT_VERSION,
                },
            )
            db.add(claim)
            db.flush()
            if source_id:
                db.add(
                    ClaimEvidence(
                        claim_id=claim.id,
                        document_id=int(source_id),
                        evidence_type="supports",
                        summary=f"Generated from {source_type} source.",
                        confidence=claim.confidence,
                        source_tier=classify_source(source_type).key,
                        metadata_={"automatic": True, "generator": PROMPT_VERSION},
                    )
                )

    def _confidence_score(self, valuation: dict, facts: dict) -> int:
        if valuation.get("status") == "insufficient_data":
            return 15
        if not facts:
            return 25
        if valuation.get("publishable"):
            return 85
        return 55

    def _rating(self, margin_of_safety: float | None, audit_passed: bool, status: str | None) -> str:
        if status == "insufficient_data":
            return "insufficient_data"
        if not audit_passed:
            return "blocked"
        if margin_of_safety is None:
            return "incomplete_price"
        if margin_of_safety > 0.30:
            return "attractive"
        if margin_of_safety < -0.20:
            return "expensive"
        return "watch"

    def _executive_summary(self, company: Company, valuation: dict) -> str:
        source = (valuation.get("trace") or {}).get("input_source", "unknown")
        engine = (valuation.get("trace") or {}).get("engine", "unknown")
        if valuation.get("status") == "insufficient_data":
            missing = ", ".join(valuation.get("missing_inputs") or []) or "required financial inputs"
            return (
                f"{company.ticker} valuation is NOT PUBLISHABLE ({engine}). "
                f"Missing: {missing}. No fair value should be trusted until inputs are sourced."
            )
        return (
            f"{company.ticker} is in the {company.company_type} bucket (engine={engine}). "
            f"Valuation input source: {source}. "
            "This version uses deterministic valuation traces and source-audited claims."
        )

    def _build_claims(
        self,
        company: Company,
        facts: dict[str, FinancialFact],
        valuation: dict,
    ) -> list[dict]:
        """Build structured claims. Metadata is non-material; facts are material."""
        claims: list[dict] = []

        # Non-material metadata — must not gate the audit as unsupported "financial" claims.
        claims.append(
            {
                "claim_id": f"{company.ticker}:company_type",
                "subject": company.ticker,
                "predicate": "company_type",
                "object": company.company_type,
                "claim": f"{company.ticker} is tracked as {company.company_type}.",
                "source_id": None,
                "source_type": "company_master",
                "confidence": 1.0,
                "material": False,
                "materiality": "metadata",
                "verification_state": "internal",
            }
        )
        claims.append(
            {
                "claim_id": f"{company.ticker}:valuation_model",
                "subject": company.ticker,
                "predicate": "valuation_model",
                "object": company.valuation_model,
                "claim": f"Valuation method selected: {company.valuation_model}.",
                "source_id": None,
                "source_type": "company_master",
                "confidence": 1.0,
                "material": False,
                "materiality": "metadata",
                "verification_state": "internal",
            }
        )

        for metric, fact in facts.items():
            claims.append(
                {
                    "claim_id": f"{company.ticker}:{metric}:{fact.period}",
                    "subject": company.ticker,
                    "predicate": metric,
                    "object": float(fact.value),
                    "unit": fact.unit,
                    "period": fact.period,
                    "claim": f"{company.ticker} {metric} is {fact.value} for {fact.period}.",
                    "source_id": fact.source_id,
                    "source_type": fact.source_type,
                    "source_document_id": fact.source_id,
                    "confidence": float(fact.confidence),
                    "material": metric
                    in {"revenue", "free_cash_flow", "net_debt", "shares_diluted", "fcf_margin"},
                    "materiality": "high"
                    if metric in {"revenue", "free_cash_flow", "shares_diluted"}
                    else "medium",
                    "verification_state": "reported" if fact.is_reported else "derived",
                }
            )

        if valuation.get("status") == "insufficient_data":
            claims.append(
                {
                    "claim_id": f"{company.ticker}:valuation_blocked",
                    "subject": company.ticker,
                    "predicate": "valuation_status",
                    "object": "insufficient_data",
                    "claim": (
                        f"{company.ticker} fair value is blocked pending: "
                        f"{', '.join(valuation.get('missing_inputs') or [])}."
                    ),
                    "source_id": None,
                    "source_type": "valuation_engine",
                    "confidence": 1.0,
                    "material": False,
                    "materiality": "process",
                    "verification_state": "system",
                }
            )

        return claims

    def _facts_markdown(self, facts: dict[str, FinancialFact]) -> str:
        if not facts:
            return (
                "No coherent financial snapshot is available. "
                "Ingest SEC/FMP facts before any publishable valuation."
            )
        rows = [
            "| Metric | Value | Unit | Period | Source |",
            "| --- | ---: | --- | --- | --- |",
        ]
        for metric, fact in facts.items():
            rows.append(
                f"| {metric} | {fact.value} | {fact.unit} | {fact.period} | "
                f"{fact.source_type} #{fact.source_id or 'n/a'} |"
            )
        return "\n".join(rows)

    def _valuation_markdown(self, valuation: dict) -> str:
        if valuation.get("status") == "insufficient_data":
            missing = "\n".join(f"- {item}" for item in (valuation.get("missing_inputs") or []))
            return (
                "**NO VALUATION — insufficient data**\n\n"
                f"Engine: `{(valuation.get('trace') or {}).get('engine', 'unknown')}`\n\n"
                f"Missing:\n{missing or '- required inputs'}\n\n"
                "CavaAI will not publish a fair value from bootstrap assumptions."
            )

        price = valuation.get("current_price")
        mos = valuation.get("margin_of_safety")
        price_txt = f"{price:.2f}" if price is not None else "N/A (no market price)"
        mos_txt = f"{mos:.1%}" if mos is not None else "N/A (requires market price)"

        def fmt(v):
            return f"{v:.2f}" if v is not None else "N/A"

        return "\n".join(
            [
                f"- Status: `{valuation.get('status')}` publishable={valuation.get('publishable')}",
                f"- Current price: {price_txt}",
                f"- Bear value: {fmt(valuation.get('bear_value'))}",
                f"- Base value: {fmt(valuation.get('base_value'))}",
                f"- Bull value: {fmt(valuation.get('bull_value'))}",
                f"- Expected value: {fmt(valuation.get('expected_value'))}",
                f"- Margin of safety: {mos_txt}",
                f"- Input source: {(valuation.get('trace') or {}).get('input_source', 'unknown')}",
                f"- Engine: {(valuation.get('trace') or {}).get('engine', 'unknown')}",
            ]
        )

    def _moat_markdown(self, company: Company, valuation: dict) -> str:
        moat = valuation.get("moat") or empty_moat_framework(
            company.company_type, company.factor_tags or [], company.special_risks or []
        )
        lines = [
            moat.get("note", "Requires sourced evidence before final qualitative claims."),
            "",
            "| Type | Strength | Trend | Confidence | Status |",
            "| --- | ---: | --- | ---: | --- |",
        ]
        for item in moat.get("moats") or []:
            lines.append(
                f"| {item.get('type')} | {item.get('strength', 0):.2f} | {item.get('trend')} | "
                f"{item.get('confidence', 0):.2f} | {item.get('status')} |"
            )
        return "\n".join(lines)

    def _render_markdown(
        self,
        company: Company,
        valuation: dict,
        audit: dict,
        facts: dict[str, FinancialFact],
        *,
        long_term_model: dict,
        version: int,
    ) -> str:
        reverse = valuation.get("reverse_dcf") or {}
        required_growth = reverse.get("required_revenue_growth")
        reverse_line = (
            f"Required revenue growth: {required_growth:.1%}"
            if required_growth is not None
            else "Reverse DCF unavailable (missing market price or valuation inputs)."
        )
        scenario_style = (valuation.get("trace") or {}).get("scenario_style", "n/a")
        framework = long_term_model.get("framework") or {}
        mandatory_missing = long_term_model.get("missing_mandatory_drivers") or []
        market_opportunity = long_term_model.get("market_opportunity") or {}

        return f"""# {company.ticker} Thesis v{version}

## 1. Executive Summary
{company.name} is tracked as `{company.company_type}` with model `{company.valuation_model}`.
Valuation input source: `{(valuation.get("trace") or {}).get("input_source", "unknown")}`.
Engine: `{(valuation.get("trace") or {}).get("engine", "unknown")}`.

## 2. One-Line Thesis
The investable question is whether the evidence supports the assumptions behind the selected model, not whether a model output looks attractive in isolation.

## 3. Business Model
Sector: {company.sector}. Industry: {company.industry}.
Company-specific framework: `{framework.get("key", "unknown")}`. Primary question: {framework.get("primary_question", "unknown")}.
Mandatory drivers missing: {", ".join(mandatory_missing) if mandatory_missing else "none"}.

## 4. Latest Results
{self._facts_markdown(facts)}

## 5. Historical Financials
Stored in `financial_facts` and `financial_statements` once ingested. Snapshot builder enforces period coherence.

## 6. Free Cash Flow
Derived only from coherent snapshot facts (same fiscal anchor). Bootstrap FCF margins are disabled.

## 7. Balance Sheet
Net debt / cash / shares must align with the income-statement anchor period (or a compatible instant).

## 8. Capital Allocation
Tracked through filings, calls, buybacks, dilution and dividends. Funding-gap dilution replaces fixed $100 capital raises when cash/capex facts exist.

## 9. Management And Calls
Call claims are stored separately and later verified against reported outcomes.

## 10. News And Catalysts
Material news updates require source audit and human approval before thesis versioning.

## 11. Risks
{", ".join(company.special_risks)}

## 12. Competition And Moat
{self._moat_markdown(company, valuation)}

## 13. Valuation
{self._valuation_markdown(valuation)}

### Long-Term Fundamental Modeling Engine
Persisted model version: `{(long_term_model.get("persistence") or {}).get("version")}`.
Model status: `{long_term_model.get("status")}`. Market-opportunity verdict: `{(market_opportunity.get("verdict") or {}).get("label", "unknown")}`.

## 14. Reverse DCF
{reverse_line}

## 15. Bear / Base / Bull
Scenario style: `{scenario_style}`. Probabilities and causal drivers are stored in the calculation trace.

## 16. Red Team
Primary red-team question: what assumption would break first if the next filing contradicts the current model?

## 17. What Would Invalidate The Thesis
Unsupported claims, missing calculation traces, adverse primary filings, incoherent snapshots, or material assumption drift.

## 18. What To Watch
{", ".join(company.special_sources)}

## 19. Source Audit
Passed: {audit["passed"]}
Coverage score: {audit["source_coverage_score"]}
Unsupported claims: {audit["unsupported_claims"]}

## 20. Sources
Company master seed, then SEC/FMP/IR/FRED/GDELT documents as ingested. Fingerprint: evidence-set hash drives versioning.
"""
