from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company
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
        peers, basis = self._find_peers(db, company, limit)
        participants = [company, *peers]
        rows = [self._company_row(db, participant, metric_names, participant.id == company.id, refresh) for participant in participants]

        return {
            "ticker": company.ticker,
            "basis": basis,
            "peer_count": len(peers),
            "metrics": metric_names,
            "benchmarks": self._benchmarks(rows, metric_names),
            "companies": rows,
        }

    def _find_peers(self, db: Session, company: Company, limit: int) -> tuple[list[Company], str]:
        peers = list(
            db.scalars(
                select(Company)
                .where(Company.id != company.id, Company.industry == company.industry)
                .order_by(Company.ticker)
                .limit(limit)
            ).all()
        )
        basis = "industry"

        if len(peers) < limit:
            existing_ids = {peer.id for peer in peers} | {company.id}
            sector_peers = list(
                db.scalars(
                    select(Company)
                    .where(~Company.id.in_(existing_ids), Company.sector == company.sector)
                    .order_by(Company.ticker)
                    .limit(limit - len(peers))
                ).all()
            )
            peers.extend(sector_peers)
            if sector_peers and basis == "industry":
                basis = "industry_then_sector"

        return peers, basis

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
