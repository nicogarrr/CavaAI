"""Stage 6c: durable graph approval interrupt service tests.

Distinct from test_thesis_approval.py, which covers the Telegram
human-in-the-loop on the classic ThesisService path.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, ThesisVersion, WorkflowRun
from app.services.thesis_graph_approval_service import (
    DECIDED_STATUSES,
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


def _publish(db: Session, ticker: str) -> None:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    db.add(
        ThesisVersion(
            company_id=company.id, version=1, status="published",
            thesis_markdown="# t", executive_summary="s",
        )
    )
    db.commit()


def test_decisions_match_graph_contract():
    assert set(DECISIONS) == {"approve", "request_changes"}
    assert DECIDED_STATUSES == {"published", "approved", "changes_requested"}


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


def test_decide_approve_publishes_only_when_a_thesis_is_published(db, service):
    _company(db)
    _publish(db, "AAPL")
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    result = service.decide(db, thread_id=thread_id, decision="approve", notes="ok", actor="tester")
    assert result["status"] == "published"
    assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert result["approval"] == {"decision": "approve", "notes": "ok", "actor": "tester"}


def test_decide_approve_without_a_published_thesis_ends_approved(db, service):
    """Aprobar no publica nada: sin ThesisVersion publicada el estado es 'approved'."""
    _company(db)
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    result = service.decide(db, thread_id=thread_id, decision="approve")
    assert result["status"] == "approved"
    assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)


def test_start_never_reports_an_unexecuted_thread_as_awaiting(db, service):
    _company(db)
    started = service.start(db, ticker="AAPL")
    assert started["approval_request"]["candidate_artifact"].startswith("candidate:sha256:")
    assert started["approval_request"]["candidate"]["observations"]


def test_decide_request_changes_skips_publication_node(db, service):
    _company(db)
    thread_id = service.start(db, ticker="AAPL")["thread_id"]
    result = service.decide(db, thread_id=thread_id, decision="request_changes", notes="redo")
    assert result["status"] == "changes_requested"
    assert "persisted_thesis" not in result["completed_nodes"]


def test_decide_on_decided_thread_reports_already_decided(db, service):
    _company(db)
    _publish(db, "AAPL")
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


def test_same_ticker_different_tenants_get_separate_threads(db, service):
    _company(db)
    a = service.start(db, ticker="AAPL", tenant_external_id="1")
    b = service.start(db, ticker="AAPL", tenant_external_id="2")
    assert a["thread_id"] != b["thread_id"]
    assert a["thread_id"].startswith("thesis:1:")
    assert b["thread_id"].startswith("thesis:2:")


def test_decide_rejects_thread_of_another_tenant(db, service):
    _company(db)
    a = service.start(db, ticker="AAPL", tenant_external_id="1")
    crossed = service.decide(
        db, thread_id=a["thread_id"], decision="approve", tenant_external_id="2"
    )
    assert crossed["status"] == "unknown_thread"
    # Tenant 1's approval state is untouched and still pending.
    again = service.start(db, ticker="AAPL", tenant_external_id="1")
    assert again["status"] == "awaiting_approval"
    own = service.decide(
        db, thread_id=a["thread_id"], decision="request_changes", tenant_external_id="1"
    )
    assert own["status"] == "changes_requested"
