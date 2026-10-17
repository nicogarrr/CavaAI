"""MemoryService contract tests.

El cerebro es SOLO LECTURA: la escritura desde el chat
(``maybe_write_from_chat``) quedó retirada. La recuperación sigue
ordenando por solape, importancia, recencia y afinidad de empresa.
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
