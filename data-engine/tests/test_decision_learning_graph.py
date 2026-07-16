from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Company,
    CompanyKPI,
    DecisionJournalEntry,
    ExpectationReview,
    FundamentalForecast,
    FundamentalModelVersion,
    InvestmentPrinciple,
    KnowledgeDocument,
    KnowledgeGraphNode,
    Tenant,
)
from app.services.decision_learning_service import DecisionLearningService
from app.services.knowledge_graph_service import KnowledgeGraphService


def test_missed_expectation_becomes_approved_lesson_and_graph_evidence():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="learning-test", name="Learning test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        db.info["user_id"] = "analyst"
        company = Company(
            ticker="LEARN",
            name="Learning Co",
            exchange="TEST",
            currency="USD",
            sector="Space",
            industry="Satellite",
            company_type="space_telecom_pre_fcf",
            valuation_model="pre_revenue",
            special_sources=[],
            special_risks=[],
            factor_tags=["space", "pre_revenue", "capital_intensive"],
        )
        db.add(company)
        db.flush()
        model = FundamentalModelVersion(
            company_id=company.id,
            version=1,
            engine_version="test",
            algorithm_version="test",
            framework_key="space_network",
            horizon_years=5,
            status="ok",
            publishable=False,
            input_fingerprint="a" * 64,
            forecast_fingerprint="b" * 64,
            market_snapshot_fingerprint="c" * 64,
            valuation_snapshot_fingerprint="d" * 64,
        )
        db.add(model)
        db.flush()
        forecast = FundamentalForecast(
            model_version_id=model.id,
            company_id=company.id,
            scenario="base",
            probability=Decimal("0.6"),
            fiscal_year=2027,
            metric="shares_diluted",
            value=Decimal("100"),
            unit="shares",
        )
        decision = DecisionJournalEntry(
            company_id=company.id,
            model_version_id=model.id,
            decision="buy",
            rationale="Funding plan appears sufficient without major dilution.",
            what_must_be_true=["Share count remains below 110"],
            status="open",
        )
        db.add_all([forecast, decision])
        db.flush()
        review = ExpectationReview(
            company_id=company.id,
            model_version_id=model.id,
            forecast_id=forecast.id,
            semantics="lower_is_better",
            fiscal_year=2027,
            metric="shares_diluted",
            expected_value=Decimal("100"),
            actual_value=Decimal("140"),
            variance=Decimal("40"),
            variance_percent=Decimal("0.4"),
            status="miss",
            trace={"actual_source_type": "financial_fact"},
        )
        db.add(review)
        document = KnowledgeDocument(
            title="Capital allocation letter",
            author="Investor",
            document_type="fund_letter",
            status="ready",
        )
        db.add(document)
        db.flush()
        db.add(
            InvestmentPrinciple(
                knowledge_document_id=document.id,
                principle="Capital intensity increases external funding risk.",
                category="capital_allocation",
                exact_fragment="Capital intensity increases external funding risk.",
                author="Investor",
                applies_to_company_ids=[company.id],
                confidence=Decimal("0.9"),
                status="approved",
            )
        )
        db.add(
            CompanyKPI(
                company_id=company.id,
                metric_key="shares_diluted",
                display_name="Diluted shares",
                canonical_unit="shares",
                required=True,
            )
        )
        db.commit()

        lesson = DecisionLearningService().propose_from_reviews(db, company)[0]
        assert lesson.taxonomy == "underestimating_dilution"
        assert lesson.expectation_review_id == review.id
        with pytest.raises(ValueError, match="Complete lesson fields"):
            DecisionLearningService().decide(
                db, lesson, action="approve", actor="analyst"
            )
        DecisionLearningService().update(
            db,
            lesson,
            taxonomy="underestimating_dilution",
            cause="Funding needs were modeled too optimistically.",
            error="I ignored the probability of an equity raise.",
            lesson_text="Model funding and dilution before valuing the equity.",
            future_application="Require a bear-case share count in every pre-revenue model.",
        )
        approved = DecisionLearningService().decide(
            db, lesson, action="approve", actor="analyst"
        )
        assert approved.status == "approved"
        assert decision.status == "reviewed"

        synced = KnowledgeGraphService().sync(db)
        assert synced["nodes"] > 0
        assert synced["edges"] > 0
        company_node = db.scalar(
            select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.node_key == f"company:{company.id}"
            )
        )
        assert company_node is not None
        neighborhood = KnowledgeGraphService().neighborhood(
            db, company_node.id, depth=3
        )
        keys = {node["key"] for node in neighborhood["nodes"]}
        assert {
            "concept:capital_intensity",
            "concept:funding_risk",
            "concept:dilution",
            f"lesson:{approved.id}",
            "author:investor",
        } <= keys
        assert any(
            edge["type"] == "produced_lesson"
            for edge in neighborhood["edges"]
        )
