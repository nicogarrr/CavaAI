"""Stage 6b: shadow comparison service tests."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import WorkflowRun
from app.models.entities import Base, Company, ThesisVersion
from app.services.thesis_shadow_service import (
    PHASE_TO_NODE,
    ThesisShadowService,
    WORKFLOW_NAME,
)
from app.services.thesis_job_service import THESIS_PHASES
from app.workflows.thesis_graph import THESIS_GRAPH_NODES


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session, ticker: str = "AAPL") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_unknown_company(db):
    assert ThesisShadowService().run(db, ticker="NOPE")["status"] == "unknown_company"


def test_shadow_runs_graph_and_records_comparison(db):
    _company(db)
    db.add(ThesisVersion(company_id=1, version=1, status="published", thesis_markdown="# t", executive_summary="s"))
    db.commit()
    result = ThesisShadowService().run(db, ticker="AAPL")
    execution = result["graph_execution"]
    assert execution["nodes_in_order"] is True
    assert execution["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert execution["final_status"] == "published"
    assert execution["idempotent_retry"] is True
    assert execution["retry_added_nodes"] == []
    assert result["phase_mapping"]["complete"] is True
    assert result["status_semantics"]["classic_latest_version"] == {
        "version": 1,
        "status": "published",
    }
    assert result["shadow_only"] is True
    # Durable run recorded with the full comparison payload.
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.workflow_name == WORKFLOW_NAME))
    assert run is not None and run.status == "succeeded"
    assert run.result_payload["graph_execution"]["idempotent_retry"] is True


def test_shadow_without_classic_thesis_reports_divergence(db):
    _company(db)
    result = ThesisShadowService().run(db, ticker="AAPL")
    assert any("no persisted thesis version" in d for d in result["divergences"])
    # The expected 6b skeleton divergence is always stated, not hidden.
    assert any("expected at 6b" in d for d in result["divergences"])


def test_every_classic_phase_is_mapped():
    assert set(THESIS_PHASES) <= set(PHASE_TO_NODE)
    for node in PHASE_TO_NODE.values():
        assert node in THESIS_GRAPH_NODES


def test_idempotency_key_replays_stored_run(db):
    _company(db)
    service = ThesisShadowService()
    first = service.run(db, ticker="AAPL", idempotency_key="shadow-aapl-1")
    assert not first.get("idempotent_replay")
    second = service.run(db, ticker="AAPL", idempotency_key="shadow-aapl-1")
    assert second["idempotent_replay"] is True
    runs = db.scalars(
        select(WorkflowRun).where(WorkflowRun.workflow_name == WORKFLOW_NAME)
    ).all()
    assert len(runs) == 1
