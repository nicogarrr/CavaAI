from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, aliased

from app.models import (
    CalculatedMetric,
    Claim,
    Company,
    Document,
    FinancialFact,
    FundamentalModelVersion,
    ResearchAlert,
    ResearchReview,
    ThesisChange,
    ThesisVersion,
    ValuationModel,
)
from app.schemas import CompanySnapshotOut


class CompanySnapshotService:
    """Build the small workspace bootstrap exclusively from persisted rows.

    This service deliberately contains no calculator, model builder, graph
    builder, document chunk loader or commit. Refreshes belong to explicit POST
    endpoints so a GET can be cached, retried and observed without side effects.
    """

    def build(self, db: Session, company: Company) -> CompanySnapshotOut:
        thesis = db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )
        model = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        valuation_model = db.scalar(
            select(ValuationModel)
            .where(ValuationModel.company_id == company.id)
            .order_by(desc(ValuationModel.version), desc(ValuationModel.created_at))
            .limit(1)
        )
        recent_changes = list(
            db.scalars(
                select(ThesisChange)
                .where(ThesisChange.company_id == company.id)
                .order_by(desc(ThesisChange.created_at))
                .limit(10)
            ).all()
        )
        counts = self._counts(db, company.id)
        return self._assemble(company, thesis, model, valuation_model, recent_changes, counts)

    def build_many(
        self, db: Session, companies: list[Company]
    ) -> dict[int, CompanySnapshotOut]:
        """Snapshots de N empresas con queries agregadas (anti fan-out del indice).

        El indice de research pedia un snapshot por empresa: 5 round trips x
        40 empresas = ~200 queries contra Postgres y 40 llamadas HTTP por
        visita. Aqui el ultimo thesis/modelo/valoracion por empresa sale con
        row_number() particionado por company_id, los ultimos 10 cambios por
        empresa con la misma ventana, y los 8 conteos agrupados con GROUP BY:
        ~13 queries para TODO el lote, independientemente de N. El caller
        acota el lote (MAX_SNAPSHOT_BATCH_TICKERS en la ruta); no hay
        proyeccion parcial de columnas, se leen las filas completas igual
        que en build().
        """
        if not companies:
            return {}
        # inspect().identity da la PK SIN consulta aunque la instancia venga
        # expirada (leer .id re-SELECTaria una por una); las filas se
        # refrescan en UNA query por IN.
        company_ids = [
            int(identity[0])
            for company in companies
            if (identity := sa_inspect(company).identity) is not None
        ]
        if not company_ids:
            return {}
        companies = list(
            db.scalars(select(Company).where(Company.id.in_(company_ids))).all()
        )
        theses = self._latest_by_company(
            db, ThesisVersion, company_ids, desc(ThesisVersion.version)
        )
        models = self._latest_by_company(
            db, FundamentalModelVersion, company_ids, desc(FundamentalModelVersion.version)
        )
        valuations = self._latest_by_company(
            db,
            ValuationModel,
            company_ids,
            desc(ValuationModel.version),
            desc(ValuationModel.created_at),
        )
        changes = self._recent_changes_many(db, company_ids)
        counts = self._counts_many(db, company_ids)
        return {
            company.id: self._assemble(
                company,
                theses.get(company.id),
                models.get(company.id),
                valuations.get(company.id),
                changes.get(company.id, []),
                counts[company.id],
            )
            for company in companies
        }

    @staticmethod
    def _latest_by_company(
        db: Session, entity: type, company_ids: list[int], *order_by
    ) -> dict[int, object]:
        """La fila mas reciente por company_id en UNA query (window function)."""
        ranked = (
            select(
                entity,
                func.row_number()
                .over(partition_by=entity.company_id, order_by=[*order_by])
                .label("rank_"),
            )
            .where(entity.company_id.in_(company_ids))
            .subquery()
        )
        aliased_entity = aliased(entity, ranked)
        rows = db.scalars(select(aliased_entity).where(ranked.c.rank_ == 1)).all()
        return {row.company_id: row for row in rows}

    @staticmethod
    def _recent_changes_many(
        db: Session, company_ids: list[int], per_company: int = 10
    ) -> dict[int, list[ThesisChange]]:
        """Los ultimos ``per_company`` cambios de cada empresa en UNA query."""
        ranked = (
            select(
                ThesisChange,
                func.row_number()
                .over(
                    partition_by=ThesisChange.company_id,
                    order_by=[desc(ThesisChange.created_at)],
                )
                .label("rank_"),
            )
            .where(ThesisChange.company_id.in_(company_ids))
            .subquery()
        )
        aliased_change = aliased(ThesisChange, ranked)
        # ORDER BY externo: la window numera cada particion, pero sin orden
        # de la consulta exterior las filas salen en orden arbitrario.
        rows = db.scalars(
            select(aliased_change)
            .where(ranked.c.rank_ <= per_company)
            .order_by(ranked.c.company_id, desc(ranked.c.created_at))
        ).all()
        grouped: dict[int, list[ThesisChange]] = {}
        for row in rows:
            grouped.setdefault(row.company_id, []).append(row)
        return grouped

    @staticmethod
    def _counts_many(db: Session, company_ids: list[int]) -> dict[int, dict[str, int]]:
        """Los 8 conteos por empresa: una query GROUP BY por tabla, no por empresa."""

        def grouped(entity: type, *extra_where) -> dict[int, int]:
            stmt = (
                select(entity.company_id, func.count())
                .where(entity.company_id.in_(company_ids), *extra_where)
                .group_by(entity.company_id)
            )
            return {int(cid): int(n) for cid, n in db.execute(stmt).all()}

        facts = grouped(FinancialFact)
        calculated_metrics = grouped(CalculatedMetric)
        documents = grouped(Document)
        claims = grouped(Claim)
        thesis_versions = grouped(ThesisVersion)
        model_versions = grouped(FundamentalModelVersion)
        open_reviews = grouped(
            ResearchReview, ResearchReview.status.in_(["open", "in_progress"])
        )
        open_alerts = grouped(
            ResearchAlert, ResearchAlert.status.in_(["open", "snoozed"])
        )
        return {
            company_id: {
                "facts": facts.get(company_id, 0),
                "calculated_metrics": calculated_metrics.get(company_id, 0),
                "documents": documents.get(company_id, 0),
                "claims": claims.get(company_id, 0),
                "thesis_versions": thesis_versions.get(company_id, 0),
                "model_versions": model_versions.get(company_id, 0),
                "open_reviews": open_reviews.get(company_id, 0),
                "open_alerts": open_alerts.get(company_id, 0),
            }
            for company_id in company_ids
        }

    def _assemble(
        self,
        company: Company,
        thesis: ThesisVersion | None,
        model: FundamentalModelVersion | None,
        valuation_model: ValuationModel | None,
        recent_changes: list[ThesisChange],
        counts: dict[str, int],
    ) -> CompanySnapshotOut:
        missing: list[str] = []
        if counts["documents"] == 0:
            missing.append("documents")
        if counts["facts"] == 0:
            missing.append("financial_facts")
        if thesis is None:
            missing.append("thesis")
        if model is None:
            missing.append("long_term_model")

        review_required = counts["open_reviews"] > 0 or counts["open_alerts"] > 0
        completed = 4 - len(missing)
        score = completed * 20
        if counts["calculated_metrics"] > 0:
            score += 10
        if counts["claims"] > 0:
            score += 10
        # Anti-falsa-seguridad: sin tesis no hay nota alta aunque haya
        # hechos+documentos+modelo (era 70/100 con 0 afirmaciones y sin
        # tesis). Sin afirmaciones tampoco se supera el notable.
        # Ponderación: 20 por capa (docs, facts, tesis, modelo) +10 métricas +10 claims.
        if thesis is None:
            score = min(score, 59)
        elif counts["claims"] == 0:
            score = min(score, 69)
        if counts["documents"] == counts["facts"] == counts["claims"] == 0:
            health_status = "empty"
        elif review_required:
            health_status = "review_required"
        elif missing or counts["claims"] == 0:
            # Sin afirmaciones el score queda topado (<=69): la etiqueta debe
            # acompañar al numero; "healthy" con nota topada era contradictorio.
            health_status = "incomplete"
        else:
            health_status = "healthy"

        thesis_summary = None
        if thesis is not None:
            thesis_summary = {
                "id": thesis.id,
                "version": thesis.version,
                "status": thesis.status,
                "executive_summary": thesis.executive_summary,
                "rating": thesis.rating,
                "current_price": thesis.current_price,
                "bear_value": thesis.bear_value,
                "base_value": thesis.base_value,
                "bull_value": thesis.bull_value,
                "expected_value": thesis.expected_value,
                "margin_of_safety": thesis.margin_of_safety,
                "data_confidence_score": thesis.data_confidence_score,
                "source_coverage_score": thesis.source_coverage_score,
                "hypothesis": getattr(thesis, "hypothesis", None),
                "catalysts": getattr(thesis, "catalysts", None),
                "invalidation_criteria": getattr(thesis, "invalidation_criteria", None),
                "scenario_probabilities": getattr(thesis, "scenario_probabilities", None),
                "created_at": thesis.created_at,
            }

        model_summary = None
        if model is not None:
            model_summary = {
                "id": model.id,
                "version": model.version,
                "engine_version": model.engine_version,
                "algorithm_version": model.algorithm_version,
                "framework_key": model.framework_key,
                "horizon_years": model.horizon_years,
                "status": model.status,
                "publishable": model.publishable,
                "input_fingerprint": model.input_fingerprint,
                "forecast_fingerprint": model.forecast_fingerprint,
                "market_snapshot_fingerprint": model.market_snapshot_fingerprint,
                "valuation_snapshot_fingerprint": model.valuation_snapshot_fingerprint,
                "code_commit_sha": model.code_commit_sha,
                "scenario_probabilities": {
                    str(key): float(value) if value is not None else None
                    for key, value in (model.scenario_probabilities or {}).items()
                },
                "created_at": model.created_at,
            }

        return CompanySnapshotOut.model_validate(
            {
                "company": company,
                "latest_thesis": thesis_summary,
                "valuation_summary": {
                    "model_id": valuation_model.id if valuation_model else None,
                    "model_type": (
                        valuation_model.model_type
                        if valuation_model
                        else company.valuation_model
                    ),
                    "version": valuation_model.version if valuation_model else None,
                    "status": (
                        valuation_model.status if valuation_model else "not_generated"
                    ),
                    "current_price": thesis.current_price if thesis else None,
                    "bear_value": thesis.bear_value if thesis else None,
                    "base_value": thesis.base_value if thesis else None,
                    "bull_value": thesis.bull_value if thesis else None,
                    "expected_value": thesis.expected_value if thesis else None,
                    "margin_of_safety": thesis.margin_of_safety if thesis else None,
                    "updated_at": (
                        valuation_model.updated_at if valuation_model else None
                    ),
                },
                "model_summary": model_summary,
                "research_health": {
                    "score": min(100, score),
                    "status": health_status,
                    "missing": missing,
                    "review_required": review_required,
                },
                "counts": counts,
                "recent_changes": recent_changes,
            },
            from_attributes=True,
        )

    @staticmethod
    def _counts(db: Session, company_id: int) -> dict[str, int]:
        """Los 8 conteos en UNA sola query (anti 8 round-trips por snapshot)."""
        row = db.execute(
            select(
                select(func.count())
                .select_from(FinancialFact)
                .where(FinancialFact.company_id == company_id)
                .scalar_subquery()
                .label("facts"),
                select(func.count())
                .select_from(CalculatedMetric)
                .where(CalculatedMetric.company_id == company_id)
                .scalar_subquery()
                .label("calculated_metrics"),
                select(func.count())
                .select_from(Document)
                .where(Document.company_id == company_id)
                .scalar_subquery()
                .label("documents"),
                select(func.count())
                .select_from(Claim)
                .where(Claim.company_id == company_id)
                .scalar_subquery()
                .label("claims"),
                select(func.count())
                .select_from(ThesisVersion)
                .where(ThesisVersion.company_id == company_id)
                .scalar_subquery()
                .label("thesis_versions"),
                select(func.count())
                .select_from(FundamentalModelVersion)
                .where(FundamentalModelVersion.company_id == company_id)
                .scalar_subquery()
                .label("model_versions"),
                select(func.count())
                .select_from(ResearchReview)
                .where(
                    ResearchReview.company_id == company_id,
                    ResearchReview.status.in_(["open", "in_progress"]),
                )
                .scalar_subquery()
                .label("open_reviews"),
                select(func.count())
                .select_from(ResearchAlert)
                .where(
                    ResearchAlert.company_id == company_id,
                    ResearchAlert.status.in_(["open", "snoozed"]),
                )
                .scalar_subquery()
                .label("open_alerts"),
            )
        ).one()
        return {
            "facts": int(row.facts or 0),
            "calculated_metrics": int(row.calculated_metrics or 0),
            "documents": int(row.documents or 0),
            "claims": int(row.claims or 0),
            "thesis_versions": int(row.thesis_versions or 0),
            "model_versions": int(row.model_versions or 0),
            "open_reviews": int(row.open_reviews or 0),
            "open_alerts": int(row.open_alerts or 0),
        }
