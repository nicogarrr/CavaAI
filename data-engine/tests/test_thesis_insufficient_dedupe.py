"""QA-6: insufficient_data equivalentes (solo cambia el precio) no apilan versiones."""
import inspect
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.core.database import SessionLocal, init_db
from app.models import Company, MarketPrice, NewsEvent, ThesisVersion
from app.seed import seed
from app.services.thesis_service import ThesisService
from tests import test_thesis_auto_ingest as base


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    base._clean_asts_evidence()


def _versions():
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == "ASTS"))
        rows = db.scalars(
            select(ThesisVersion).where(ThesisVersion.company_id == company.id).order_by(ThesisVersion.version)
        ).all()
        return [(r.id, r.version, r.status, r.updated_at) for r in rows]
    finally:
        db.close()


def _new_price():
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == "ASTS"))
        db.add(MarketPrice(company_id=company.id, date=date.today() + timedelta(days=30),
                           open=1, high=1, low=1, close=31.25, source="test"))
        db.commit()
    finally:
        db.close()


def test_generate_dedupes_price_only_change_but_not_material_or_forced(monkeypatch):
    init_db()
    seed()
    base._clean_asts_evidence()
    base._mock_all_sources(monkeypatch)
    base._seed_evidence_rows()
    client = TestClient(main.app)

    first = client.post("/api/thesis/generate", json={"ticker": "ASTS", "force_new_version": True}).json()
    assert first["status"] == "insufficient_data"
    assert "insufficient_signature" in (first["valuation_basis"] or {})
    before = _versions()

    # Solo cambia el precio: misma firma => no hay version nueva.
    _new_price()
    again = client.post("/api/thesis/generate", json={"ticker": "ASTS"}).json()
    after_price = _versions()
    assert again["id"] == first["id"]
    assert [v[:3] for v in after_price] == [v[:3] for v in before]

    # Noticia nueva = evidencia material: version nueva.
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == "ASTS"))
        db.add(NewsEvent(company_id=company.id, date=datetime.now(UTC), title="ASTS nueva noticia material",
                         source="press", url="https://example.com/n2", summary="x", event_type="partnership",
                         materiality_score=8, impact_direction="positive"))
        db.commit()
    finally:
        db.close()
    after_news = client.post("/api/thesis/generate", json={"ticker": "ASTS"}).json()
    assert after_news["id"] != first["id"]
    assert len(_versions()) == len(before) + 1

    # force_new_version siempre crea.
    forced = client.post("/api/thesis/generate", json={"ticker": "ASTS", "force_new_version": True}).json()
    assert forced["id"] not in (first["id"], after_news["id"])


def _row(status, basis):
    return SimpleNamespace(status=status, valuation_basis=basis)


SIG = {"reason": "r", "engine": "e", "method": "m", "missing_inputs": ["wacc"], "material_fp": "x"}


def test_signature_requires_every_field_equal_and_explicit_previous():
    same = _row("insufficient_data", {"insufficient_signature": dict(SIG)})
    assert ThesisService._same_insufficient_signature(same, dict(SIG))
    for key, other in (("reason", "otro"), ("engine", "otro"), ("method", "otro"),
                       ("missing_inputs", ["capex"]), ("material_fp", "y")):
        assert not ThesisService._same_insufficient_signature(same, {**SIG, key: other}), key
    # Sin evidencia previa explicita: nunca se deduplica.
    assert not ThesisService._same_insufficient_signature(_row("insufficient_data", None), dict(SIG))
    assert not ThesisService._same_insufficient_signature(_row("insufficient_data", {}), dict(SIG))
    assert not ThesisService._same_insufficient_signature(_row("draft", {"insufficient_signature": dict(SIG)}), dict(SIG))
    assert not ThesisService._same_insufficient_signature(same, None)


def test_dedupe_check_runs_before_persisting_a_new_version():
    full = inspect.getsource(ThesisService)
    assert full.index("_same_insufficient_signature(existing, insufficient_signature)") < full.index("thesis = ThesisVersion(")
