"""Cierre de flujos a medias (auditoria verificada).

Tests hermeticos (SQLite en memoria, sin red) de los puntos del cierre:
scheduler evaluate_alert_rules cada 5 min, approve de tesis, filings
insider persistidos, telegram-status sin secretos y citas EPUB con
provenance real.
"""

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.insider import insider_filings
from app.api.routes.alerts import telegram_status
from app.api.routes.thesis import ThesisApproveRequest, _epub_citations, approve_thesis
from app.core.database import Base
from app.models.entities import (
    Claim,
    ClaimEvidence,
    Company,
    InsiderFiling,
    InsiderTransaction,
    ThesisVersion,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_SRC = (REPO_ROOT / "app" / "workers" / "scheduler.py").read_text()
DRAMATIQ_SRC = (REPO_ROOT / "app" / "workers" / "dramatiq_app.py").read_text()


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session, ticker: str = "ACME") -> Company:
    company = Company(
        ticker=ticker, name="Acme", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="operating_company",
        valuation_model="dcf", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


# (2) Job evaluate_alert_rules registrado cada 5 minutos ---------------------

def test_scheduler_registers_evaluate_alert_rules_every_5_minutes():
    tree = ast.parse(SCHEDULER_SRC)
    imported = {
        alias.name
        for stmt in ast.walk(tree)
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "app.workers.dramatiq_app"
        for alias in stmt.names
    }
    assert "evaluate_alert_rules" in imported
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords}
        job_id = keywords.get("job_id")
        minutes = keywords.get("minutes")
        if (
            isinstance(job_id, ast.Constant) and job_id.value == "alert_rule_evaluation"
            and isinstance(minutes, ast.Constant) and minutes.value == 5
        ):
            found = True
    assert found, "falta job alert_rule_evaluation con minutes=5 en scheduler.py"


def test_evaluate_alert_rules_actor_exists_in_dramatiq_app():
    tree = ast.parse(DRAMATIQ_SRC)

    def _is_actor_decorator(decorator: ast.expr) -> bool:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        return isinstance(target, ast.Attribute) and target.attr == "actor"

    actors = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(_is_actor_decorator(d) for d in node.decorator_list)
    }
    assert "evaluate_alert_rules" in actors


# (7) POST /thesis/{ticker}/approve ------------------------------------------

def test_approve_thesis_transitions_status(db):
    company = _company(db)
    db.add(ThesisVersion(
        company_id=company.id, version=1, status="draft",
        thesis_markdown="# t", executive_summary="e",
    ))
    db.commit()
    result = approve_thesis(
        "ACME", ThesisApproveRequest(decision="approved", actor="nico"), db=db
    )
    assert result["status"] == "approved"
    assert result["decision"] == "approved"
    assert result["actor"] == "nico"
    assert result["version"] == 1
    assert result["telegram_auto_approval"] == "future"
    stored = db.query(ThesisVersion).one()
    assert stored.status == "approved"


def test_approve_thesis_rejects_and_404s_without_thesis(db):
    _company(db, ticker="EMPTY")
    with pytest.raises(HTTPException) as exc:
        approve_thesis("EMPTY", ThesisApproveRequest(decision="approved"), db=db)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        approve_thesis("NOPE", ThesisApproveRequest(decision="approved"), db=db)
    assert exc.value.status_code == 404


def test_approve_thesis_rejects_invalid_decision():
    with pytest.raises(ValidationError):
        ThesisApproveRequest.model_validate({"decision": "maybe", "actor": "x"})


# (9) GET /api/insider/filings ------------------------------------------------

def _filing(db: Session, ticker: str = "ACME") -> InsiderFiling:
    filing = InsiderFiling(
        accession_number="0001234567-24-000201", form="4",
        issuer_cik="1234567", issuer_ticker=ticker,
        filing_date="2024-03-16", parser_version="1.1",
        source_url="https://www.sec.gov/Archives/edgar/data/1234567/f4.xml",
    )
    db.add(filing)
    db.commit()
    db.add(InsiderTransaction(
        fingerprint="fp1", filing_id=filing.id,
        accession_number=filing.accession_number, form="4",
        issuer_ticker=ticker, insider="Jane Doe", code="P",
        shares=1000.0, price=150.0, value=150000.0, tx_date="2024-03-15",
    ))
    db.commit()
    return filing


def test_insider_filings_returns_persisted_rows(db):
    _filing(db)
    result = insider_filings("ACME", 20, db=db)
    assert result["status"] == "ok"
    assert result["count"] == 1
    filing = result["filings"][0]
    assert filing["accession_number"] == "0001234567-24-000201"
    assert filing["transaction_count"] == 1
    assert filing["transactions"][0]["insider"] == "Jane Doe"


def test_insider_filings_unknown_ticker_is_empty_not_500(db):
    result = insider_filings("ZZZZ", 20, db=db)
    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["filings"] == []


# (2) telegram-status sin secretos --------------------------------------------

def test_telegram_status_exposes_presence_only():
    result = telegram_status()
    assert set(result) == {"enabled", "has_bot_token", "has_chat_id", "configured"}
    assert all(isinstance(value, bool) for value in result.values())
    assert result["configured"] == (
        result["enabled"] and result["has_bot_token"] and result["has_chat_id"]
    )


# (8) EPUB con provenance real -------------------------------------------------

def test_epub_citations_carry_source_id_and_locator(db):
    company = _company(db)
    claim = Claim(company_id=company.id, statement="Acme crece al 20%")
    db.add(claim)
    db.commit()
    db.add(ClaimEvidence(
        claim_id=claim.id, document_id=7, document_chunk_id=9,
        evidence_type="supports", summary="10-K 2024, p. 42",
        source_url="https://www.sec.gov/filing", source_tier="primary",
    ))
    lonely = Claim(company_id=company.id, statement="Sin evidencia")
    db.add(lonely)
    db.commit()
    citations = _epub_citations(db, [claim, lonely])
    assert len(citations) == 2
    assert "doc:7" in citations[0] and "chunk:9" in citations[0]
    assert f"claim:{claim.id}" in citations[0]
    assert "sin evidencia vinculada" in citations[1]


def test_epub_citations_empty_without_claims(db):
    assert _epub_citations(db, []) == []
