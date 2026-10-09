"""QA-6: insufficient_data consecutivas con el mismo motivo no crean version nueva."""
import inspect

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, SourceAudit, ThesisVersion
from app.services.thesis_service import ThesisService
from tests.test_ibkr_import import _tenant_session

PREFIX = "Faltan entradas de valoración (variables del modelo): "


def _setup(status="insufficient_data", fixes=None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    company = Company(ticker="ASTS", name="AST", currency="USD", exchange="NASDAQ", company_type="operating", valuation_model="standard_dcf")
    db.add(company)
    db.flush()
    thesis = ThesisVersion(
        company_id=company.id, version=1, status=status, thesis_markdown="x",
        executive_summary="x", rating=status, data_confidence_score=0,
        source_coverage_score=0, red_team_score=0, valuation_risk_score=0,
    )
    db.add(thesis)
    db.flush()
    db.add(SourceAudit(
        thesis_version_id=thesis.id, passed=False, source_coverage_score=0,
        unsupported_claims=[], weak_claims=[], data_conflicts=[], required_fixes=fixes or [],
    ))
    db.flush()
    return db, thesis


def _svc():
    return ThesisService.__new__(ThesisService)


def test_same_missing_inputs_is_same_reason():
    db, thesis = _setup(fixes=[PREFIX + "wacc, revenue"])
    assert _svc()._same_insufficient_reason(
        db, thesis, {"status": "insufficient_data", "missing_inputs": ["revenue", "wacc"]}
    )
    db.close()


def test_different_missing_inputs_creates_new_version():
    db, thesis = _setup(fixes=[PREFIX + "wacc"])
    assert not _svc()._same_insufficient_reason(
        db, thesis, {"status": "insufficient_data", "missing_inputs": ["wacc", "capex"]}
    )
    db.close()


def test_never_dedupes_when_either_side_is_not_insufficient():
    db, thesis = _setup(status="draft", fixes=[])
    assert not _svc()._same_insufficient_reason(db, thesis, {"status": "insufficient_data"})
    db.close()
    db, thesis = _setup(fixes=[])
    assert not _svc()._same_insufficient_reason(db, thesis, {"status": "partial"})
    db.close()


def test_no_missing_inputs_on_both_sides_matches():
    db, thesis = _setup(fixes=[])
    assert _svc()._same_insufficient_reason(db, thesis, {"status": "insufficient_data"})
    db.close()


def test_dedupe_runs_before_persisting_a_new_version():
    src = inspect.getsource(ThesisService.generate) if hasattr(ThesisService, "generate") else ""
    full = inspect.getsource(ThesisService)
    assert full.index("_same_insufficient_reason(db, existing, valuation)") < full.index("thesis = ThesisVersion(")
    assert src is not None
