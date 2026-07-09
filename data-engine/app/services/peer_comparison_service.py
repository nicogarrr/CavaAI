from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact, PeerRelationship
from app.services.metric_calculation_service import METRIC_DEFINITIONS, MetricCalculationService, MetricResult


DEFAULT_PEER_METRICS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "fcf_margin",
    "roe",
    "roa",
    "roic",
    "fcf_conversion",
    "net_debt_to_ebitda",
]


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


class PeerComparisonService:
    def __init__(self) -> None:
        self.metric_service = MetricCalculationService()

    def compare(
        self,
        db: Session,
        company: Company,
        limit: int = 8,
        metrics: list[str] | None = None,
        refresh: bool = False,
    ) -> dict:
        metric_names = [metric for metric in (metrics or DEFAULT_PEER_METRICS) if metric in METRIC_DEFINITIONS]
        peers, basis, selection_trace = self._find_peers(db, company, limit)
        participants = [company, *peers]
        rows = [self._company_row(db, participant, metric_names, participant.id == company.id, refresh) for participant in participants]

        return {
            "ticker": company.ticker,
            "basis": basis,
            "selection_trace": selection_trace,
            "peer_count": len(peers),
            "metrics": metric_names,
            "benchmarks": self._benchmarks(rows, metric_names),
            "companies": rows,
        }

    def _find_peers(
        self, db: Session, company: Company, limit: int
    ) -> tuple[list[Company], str, dict]:
        manual_rows = list(
            db.scalars(
                select(PeerRelationship)
                .where(
                    PeerRelationship.company_id == company.id,
                    PeerRelationship.selected.is_(True),
                )
                .order_by(desc(PeerRelationship.score))
            ).all()
        )
        manual_ids = [row.peer_company_id for row in manual_rows]
        manual_companies = (
            {
                peer.id: peer
                for peer in db.scalars(
                    select(Company).where(Company.id.in_(manual_ids))
                ).all()
            }
            if manual_ids
            else {}
        )
        selected: list[Company] = [
            manual_companies[peer_id]
            for peer_id in manual_ids
            if peer_id in manual_companies
        ][:limit]
        selected_ids = {peer.id for peer in selected} | {company.id}

        candidates = list(
            db.scalars(
                select(Company).where(Company.id != company.id)
            ).all()
        )
        target_market_cap = self._latest_market_cap(db, company.id)
        scored: list[tuple[float, Company, list[str], dict]] = []
        for candidate in candidates:
            if candidate.id in selected_ids:
                continue
            score, rationale, dimensions = self._peer_score(
                db, company, candidate, target_market_cap
            )
            if score <= 0:
                continue
            scored.append((score, candidate, rationale, dimensions))
        scored.sort(key=lambda item: (-item[0], item[1].ticker))
        selected.extend(
            candidate
            for _, candidate, _, _ in scored[: max(0, limit - len(selected))]
        )
        selected_ids = {peer.id for peer in selected}
        trace_rows = [
            {
                "ticker": candidate.ticker,
                "score": round(score, 4),
                "selected": candidate.id in selected_ids,
                "rationale": rationale,
                "dimensions": dimensions,
            }
            for score, candidate, rationale, dimensions in scored
        ]
        for row in manual_rows:
            peer = manual_companies.get(row.peer_company_id)
            if peer:
                trace_rows.insert(
                    0,
                    {
                        "ticker": peer.ticker,
                        "score": float(row.score),
                        "selected": True,
                        "rationale": row.rationale or ["manual peer override"],
                        "dimensions": row.selection_trace or {},
                    },
                )
        basis = (
            "manual_then_multifactor"
            if manual_rows
            else "multifactor_business_model_stage_size"
        )
        return selected, basis, {
            "method": "PEER_SELECTION_V2",
            "target_market_cap": (
                str(target_market_cap) if target_market_cap is not None else None
            ),
            "candidates": trace_rows,
        }

    def _peer_score(
        self,
        db: Session,
        target: Company,
        candidate: Company,
        target_market_cap: Decimal | None,
    ) -> tuple[float, list[str], dict]:
        score = 0.0
        rationale: list[str] = []
        dimensions: dict[str, float] = {}
        if target.industry != "Unknown" and candidate.industry == target.industry:
            score += 0.30
            dimensions["industry"] = 1.0
            rationale.append("same industry")
        elif target.sector != "Unknown" and candidate.sector == target.sector:
            score += 0.14
            dimensions["sector"] = 1.0
            rationale.append("same sector")
        if candidate.company_type == target.company_type:
            score += 0.16
            dimensions["business_model"] = 1.0
            rationale.append("same company type")
        if candidate.valuation_model == target.valuation_model:
            score += 0.10
            dimensions["capital_profile"] = 1.0
            rationale.append("same valuation/capital profile")
        target_tags = set(target.factor_tags or [])
        candidate_tags = set(candidate.factor_tags or [])
        tag_union = target_tags | candidate_tags
        tag_similarity = (
            len(target_tags & candidate_tags) / len(tag_union)
            if tag_union
            else 0
        )
        score += 0.20 * tag_similarity
        dimensions["factor_tags"] = round(tag_similarity, 4)
        if tag_similarity:
            rationale.append(
                f"shared factors: {', '.join(sorted(target_tags & candidate_tags))}"
            )
        if candidate.currency == target.currency:
            score += 0.04
            dimensions["currency"] = 1.0
        if candidate.exchange == target.exchange:
            score += 0.03
            dimensions["exchange"] = 1.0

        candidate_market_cap = self._latest_market_cap(db, candidate.id)
        if (
            target_market_cap is not None
            and target_market_cap > 0
            and candidate_market_cap is not None
            and candidate_market_cap > 0
        ):
            ratio = max(target_market_cap, candidate_market_cap) / min(
                target_market_cap, candidate_market_cap
            )
            size_score = max(0.0, 1.0 - min(float(ratio), 10.0) / 10.0)
            score += 0.17 * size_score
            dimensions["market_cap"] = round(size_score, 4)
            rationale.append(f"market-cap ratio {float(ratio):.2f}x")
        return score, rationale, dimensions

    def _latest_market_cap(
        self, db: Session, company_id: int
    ) -> Decimal | None:
        fact = db.scalar(
            select(FinancialFact)
            .where(
                FinancialFact.company_id == company_id,
                FinancialFact.metric == "market_cap",
            )
            .order_by(
                FinancialFact.fiscal_year.desc().nullslast(),
                desc(FinancialFact.created_at),
            )
            .limit(1)
        )
        return fact.value if fact else None

    def _company_row(
        self,
        db: Session,
        company: Company,
        metric_names: list[str],
        is_target: bool,
        refresh: bool,
    ) -> dict:
        results = {
            result.metric: result
            for result in self.metric_service.calculate_all(db, company, persist=refresh)
            if result.metric in metric_names
        }
        return {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "industry": company.industry,
            "is_target": is_target,
            "metrics": {metric: self._metric_payload(results.get(metric)) for metric in metric_names},
        }

    def _metric_payload(self, result: MetricResult | None) -> dict:
        if result is None:
            return {
                "value": None,
                "status": "unavailable",
                "unit": "unknown",
                "period": "unknown",
                "confidence": "0.00",
                "source_fact_ids": [],
            }
        return {
            "value": _decimal_string(result.value),
            "status": result.status,
            "unit": result.unit,
            "period": result.period,
            "confidence": _decimal_string(result.confidence),
            "source_fact_ids": result.source_fact_ids,
        }

    def _benchmarks(self, rows: list[dict], metric_names: list[str]) -> dict:
        target = next((row for row in rows if row["is_target"]), None)
        benchmarks = {}
        for metric in metric_names:
            peer_values = [
                Decimal(payload["value"])
                for row in rows
                if not row["is_target"]
                for payload in [row["metrics"][metric]]
                if payload["status"] == "ok" and payload["value"] is not None
            ]
            target_payload = target["metrics"][metric] if target else None
            target_value = (
                Decimal(target_payload["value"])
                if target_payload and target_payload["status"] == "ok" and target_payload["value"] is not None
                else None
            )
            peer_median = self._median(peer_values)
            benchmarks[metric] = {
                "peer_median": _decimal_string(peer_median),
                "peer_average": _decimal_string(sum(peer_values) / len(peer_values)) if peer_values else None,
                "peer_sample_size": len(peer_values),
                "target_value": _decimal_string(target_value),
                "target_vs_peer_median": _decimal_string(target_value - peer_median)
                if target_value is not None and peer_median is not None
                else None,
            }
        return benchmarks

    def _median(self, values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        sorted_values = sorted(values)
        midpoint = len(sorted_values) // 2
        if len(sorted_values) % 2:
            return sorted_values[midpoint]
        return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / Decimal("2")
