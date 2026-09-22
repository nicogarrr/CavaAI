"""MemoryService contract tests.

Chat memory is user-directed context: writes happen only on explicit
triggers, duplicates consolidate instead of multiplying, and retrieval
ranks overlap, importance, recency and company affinity transparently.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, MemoryItem
from app.services.memory_service import MemoryService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_write_only_on_explicit_trigger(db):
    service = MemoryService()
    assert service.maybe_write_from_chat(db, "What is the revenue trend?") is None
    assert service.maybe_write_from_chat(db, "recuerda X") is None  # too short
    item = service.maybe_write_from_chat(db, "Recuerda que vigilo el free cash flow de cerca")
    assert item is not None
    assert item.importance == 7
    assert item.scope == "portfolio"
    assert item.metadata_["write_policy"] == "triggered_by_user_instruction"


def test_duplicate_write_consolidates_instead_of_duplicating(db):
    service = MemoryService()
    text = "Recuerda que vigilo el free cash flow de cerca"
    first = service.maybe_write_from_chat(db, text)
    second = service.maybe_write_from_chat(db, "  recuerda   que VIGILO el free cash flow de cerca ")
    assert first.id == second.id
    assert db.query(MemoryItem).count() == 1


def test_company_scoped_write_stays_with_company(db):
    company = _company(db)
    service = MemoryService()
    item = service.maybe_write_from_chat(
        db, "Mi tesis sobre Apple es que el moat sigue intacto", company, scope="company"
    )
    assert item.company_id == company.id
    assert item.scope == "company"


def test_retrieval_ranks_overlap_importance_and_company(db):
    company = _company(db)
    relevant = MemoryItem(
        company_id=company.id, scope="company", memory_type="note",
        importance=5, content="Apple buyback pace supports the thesis",
        status="active", source_type="user",
    )
    important_unrelated = MemoryItem(
        company_id=None, scope="portfolio", memory_type="note",
        importance=9, content="General market heuristics and discipline",
        status="active", source_type="user",
    )
    inactive = MemoryItem(
        company_id=company.id, scope="company", memory_type="note",
        importance=10, content="Apple buyback retired note",
        status="archived", source_type="user",
    )
    db.add_all([relevant, important_unrelated, inactive])
    db.commit()

    results = MemoryService().retrieve(db, "Apple buyback", company, scope="company", limit=6)
    contents = [r.item.content for r in results]
    assert "Apple buyback retired note" not in contents  # inactive excluded
    assert contents[0] == relevant.content  # overlap + company boost wins
    # High-importance portfolio memory still surfaces (importance >= 8 rule).
    assert important_unrelated.content in contents
    assert all(r.reason.startswith("overlap=") for r in results)
