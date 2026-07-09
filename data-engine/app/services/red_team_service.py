from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CalculatedMetric,
    Claim,
    Company,
    RedTeamRun,
    ResearchReview,
    SourceAudit,
    ThesisVersion,
)
from app.services.moat_service import MoatService
from app.services.peer_analysis_service import PeerAnalysisService
from app.services.review_alert_service import ReviewAlertService
from app.services.valuation_service import ValuationService


SEVERITY_PENALTY = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
}


class RedTeamService:
    prompt_version = "red-team-v1"

    def run(
        self,
        db: Session,
        company: Company,
        thesis: ThesisVersion | None = None,
    ) -> RedTeamRun:
        thesis = thesis or db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )
        run = RedTeamRun(
            company_id=company.id,
            thesis_version_id=thesis.id if thesis else None,
            status="running",
            prompt_version=self.prompt_version,
            trace={"started_at": datetime.now(UTC).isoformat()},
        )
        db.add(run)
        db.flush()

        claims = list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.evidence))
                .where(Claim.company_id == company.id)
                .order_by(desc(Claim.materiality_score))
            ).all()
        )
        findings: list[dict] = []
        for claim in claims:
            if claim.materiality_score >= 7 and not claim.evidence:
                findings.append(
                    self._finding(
                        "high",
                        "unsupported_material_claim",
                        f"Material claim has no linked evidence: {claim.statement}",
                        claim_id=claim.id,
                    )
                )
            if claim.status in {
                "contradicted",
                "superseded",
                "stale",
                "uncertain",
            }:
                findings.append(
                    self._finding(
                        "critical"
                        if claim.status == "contradicted"
                        and claim.materiality_score >= 8
                        else "high",
                        f"claim_{claim.status}",
                        f"Claim is {claim.status}: {claim.statement}",
                        claim_id=claim.id,
                    )
                )
            if claim.materiality_score >= 7 and not (
                claim.metadata_ or {}
            ).get("invalidation_conditions"):
                findings.append(
                    self._finding(
                        "medium",
                        "missing_falsification_test",
                        f"No explicit invalidation condition: {claim.statement}",
                        claim_id=claim.id,
                    )
                )

        latest_audit = (
            db.scalar(
                select(SourceAudit)
                .where(SourceAudit.thesis_version_id == thesis.id)
                .order_by(desc(SourceAudit.created_at))
                .limit(1)
            )
            if thesis
            else None
        )
        if latest_audit and not latest_audit.passed:
            findings.append(
                self._finding(
                    "high",
                    "source_audit_failed",
                    (
                        f"Source audit failed with coverage "
                        f"{latest_audit.source_coverage_score}."
                    ),
                    source_audit_id=latest_audit.id,
                    required_fixes=latest_audit.required_fixes,
                )
            )

        valuation = ValuationService().value_company(db, company)
        if not valuation.get("publishable", False):
            findings.append(
                self._finding(
                    "high",
                    "valuation_not_publishable",
                    "Valuation is not publishable because required inputs are missing.",
                    missing_inputs=valuation.get("missing_inputs", []),
                )
            )

        latest_metrics = self._latest_metrics(db, company.id)
        roic = next(
            (
                metric
                for name, metric in latest_metrics.items()
                if name.startswith("roic") and metric.value is not None
            ),
            None,
        )
        wacc = latest_metrics.get("wacc")
        if roic and wacc and wacc.value is not None and roic.value < wacc.value:
            findings.append(
                self._finding(
                    "high",
                    "returns_below_cost_of_capital",
                    f"ROIC {roic.value} is below WACC {wacc.value}.",
                    roic_metric_id=roic.id,
                    wacc_metric_id=wacc.id,
                )
            )

        moat = MoatService().assess(db, company, persist=True)
        if moat["status"] != "evidence_backed":
            findings.append(
                self._finding(
                    "medium",
                    "moat_unproven",
                    "No moat category has sufficient sourced evidence.",
                )
            )

        peer_analysis = PeerAnalysisService().analyze(db, company)
        for disadvantage in peer_analysis["disadvantages"][:3]:
            findings.append(
                self._finding(
                    "medium",
                    "peer_disadvantage",
                    self._peer_message(disadvantage),
                    peer_dimension=disadvantage.get("dimension"),
                    claim_id=disadvantage.get("claim_id"),
                )
            )

        findings.sort(
            key=lambda item: SEVERITY_PENALTY[item["severity"]],
            reverse=True,
        )
        score = max(
            0,
            100
            - sum(
                SEVERITY_PENALTY[finding["severity"]]
                for finding in findings
            ),
        )
        strongest = (
            findings[0]["message"]
            if findings
            else "No evidence-backed bear case was identified; this may reflect insufficient coverage rather than low risk."
        )
        run.status = "completed"
        run.score = score
        run.strongest_bear_case = strongest
        run.findings = findings
        run.broken_assumptions = [
            finding["message"]
            for finding in findings
            if finding["type"]
            in {
                "claim_contradicted",
                "claim_superseded",
                "returns_below_cost_of_capital",
            }
        ]
        run.missing_risks = [
            finding["message"]
            for finding in findings
            if finding["type"]
            in {
                "unsupported_material_claim",
                "moat_unproven",
                "peer_disadvantage",
            }
        ]
        run.falsification_tests = [
            condition
            for claim in claims
            for condition in (claim.metadata_ or {}).get(
                "invalidation_conditions", []
            )
        ] or [
            "Define explicit, measurable invalidation conditions for every material thesis claim."
        ]
        run.trace = {
            **(run.trace or {}),
            "completed_at": datetime.now(UTC).isoformat(),
            "method": "deterministic_evidence_attack_v1",
            "claim_count": len(claims),
            "finding_count": len(findings),
            "valuation_status": valuation.get("status"),
            "moat_status": moat.get("status"),
            "peer_status": peer_analysis.get("status"),
        }
        if thesis:
            thesis.red_team_score = score

        if findings:
            existing = db.scalar(
                select(ResearchReview).where(
                    ResearchReview.company_id == company.id,
                    ResearchReview.review_type == "red_team",
                    ResearchReview.status.in_(["open", "in_progress"]),
                )
            )
            if existing is None:
                ReviewAlertService().create_review(
                    db,
                    review_type="red_team",
                    title=f"Red-team findings for {company.ticker}",
                    summary=strongest,
                    company_id=company.id,
                    materiality_score=10 - min(5, score // 20),
                    impact_direction="negative",
                    metadata={"red_team_run_id": run.id},
                )
        db.commit()
        db.refresh(run)
        return run

    def latest(self, db: Session, company: Company) -> RedTeamRun | None:
        return db.scalar(
            select(RedTeamRun)
            .where(RedTeamRun.company_id == company.id)
            .order_by(desc(RedTeamRun.created_at))
            .limit(1)
        )

    def _latest_metrics(
        self, db: Session, company_id: int
    ) -> dict[str, CalculatedMetric]:
        metrics = db.scalars(
            select(CalculatedMetric)
            .where(CalculatedMetric.company_id == company_id)
            .order_by(desc(CalculatedMetric.created_at))
        ).all()
        result: dict[str, CalculatedMetric] = {}
        for metric in metrics:
            result.setdefault(metric.metric, metric)
            result.setdefault(metric.definition_version.lower(), metric)
        return result

    def _finding(
        self, severity: str, finding_type: str, message: str, **trace
    ) -> dict:
        return {
            "severity": severity,
            "type": finding_type,
            "message": message,
            "trace": {key: value for key, value in trace.items() if value is not None},
        }

    def _peer_message(self, disadvantage: dict) -> str:
        if disadvantage.get("statement"):
            return disadvantage["statement"]
        return (
            f"{disadvantage.get('dimension')} trails peer median: "
            f"{disadvantage.get('target_value')} vs "
            f"{disadvantage.get('peer_median')}."
        )
