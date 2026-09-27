"""Stage 6c: durable graph approval interrupt service tests.

Distinct from test_thesis_approval.py, which covers the Telegram
human-in-the-loop on the classic ThesisService path.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, WorkflowRun
from app.services.thesis_graph_approval_service import (
    DECISIONS,
    WORKFLOW_NAME,
    ThesisGraphApprovalService,
)
from app.workflows.thesis_graph import THESIS_GRAPH_NODES


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def service(tmp_path):
    return ThesisGraphApprovalService(
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        database_url="sqlite:///./cavaai_test.db",
    )


def _company(db: Session, ticker: str = "AAPL") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_decisions_match_graph_contract():
    assert set(DECISIONS) == {"approve", "request_changes"}


def test_start_unknown_company(db, service):
    assert service.start(db, ticker="NOPE")["status"] == "unknown_company"


def test_start_pauses_at_gate_and_records_envelope(db, service):
    _company(db)
    result = service.start(db, ticker="AAPL")
    assert result["status"] == "awaiting_approval"
    assert result["awaiting_approval"] is True
    assert result["approval_request"]["type"] == "thesis_approval"
    assert result["thread_id"].startswith("thesis:default:")
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.workflow_name == WORKFLOW_NAME))
    assert run is not None and run.status == "succeeded"


def test_start_on_waiting_thread_does_not_reexecute(db, service):
    _company(db)
    first = service.start(db, ticker="AAPL")
    second = service.start(db, ticker="AAPL")  # fresh envelope, same thread
    assert second["status"] == "awaiting_approval"
    assert second["thread_id"] == first["thread_id"]


def test_start_replays_with_same_idempotency_key(db, service):
    _company(db)
    first = service.start(db, ticker="AAPL", idempotency_key="k1")
    second = service.start(db, ticker="AAPL", idempotency_key="k1")
    assert second["idempotent_replay"] is True
    assert second["thread_id"] == first["thread_id"]


def test_decide_approve_publishes(db, service):
    _company(db)
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    result = service.decide(db, thread_id=thread_id, decision="approve", notes="ok", actor="tester")
    assert result["status"] == "published"
    assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert result["approval"] == {"decision": "approve", "notes": "ok", "actor": "tester"}


def test_decide_request_changes_skips_publish(db, service):
    _company(db)
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    result = service.decide(db, thread_id=thread_id, decision="request_changes", notes="redo")
    assert result["status"] == "changes_requested"
    assert "publish" not in result["completed_nodes"]


def test_decide_on_decided_thread_reports_already_decided(db, service):
    _company(db)
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    service.decide(db, thread_id=thread_id, decision="approve")
    again = service.decide(db, thread_id=thread_id, decision="request_changes")
    assert again["already_decided"] is True
    assert again["status"] == "published"  # the first decision stands


def test_decide_unknown_thread(db, service):
    result = service.decide(db, thread_id="thesis:none:0:fp", decision="approve")
    assert result["status"] == "unknown_thread"


def test_decide_rejects_invalid_decision(db, service):
    with pytest.raises(ValueError):
        service.decide(db, thread_id="thesis:none:0:fp", decision="maybe")
