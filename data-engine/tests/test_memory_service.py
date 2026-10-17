"""MemoryService contract tests.

El chat solo escribe memoria ante "recuerda ..." explicito; la escritura amplia
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


# --- Escritura explicita: SOLO con "recuerda ..." -------------------------------

from app.services.memory_service import remember_note  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("Recuerda que prefiero inversión a largo plazo", "prefiero inversión a largo plazo"),
    ("recuerda: mi objetivo es no vender ASTS antes de 2028", "mi objetivo es no vender ASTS antes de 2028"),
    ("Por favor, recuerda que cobro dividendos en marzo", "cobro dividendos en marzo"),
    ("Remember that I hold ASTS for the long run", "I hold ASTS for the long run"),
    ("Recuerda   que\nme gusta   el value", "me gusta el value"),
])
def test_explicit_remember_instruction_is_parsed(text, expected):
    assert remember_note(text) == expected


@pytest.mark.parametrize("text", [
    "guarda esto para luego",
    "vigila ASTS y avísame",
    "mi tesis sobre MSFT es sólida",
    "watch the earnings of ASTS closely",
    "hipotesis: el margen mejora",
    "¿Recuerdas lo que te dije de ASTS?",
    "Recuerda vigilar Azure. ¿Qué evidencia tienes sobre MSFT?",
    "recuerda que",
    "recuerda ya",
    "Dime qué dijo Buffett y recuerda que es general",
    "",
])
def test_everything_else_is_not_a_memory_write(text):
    assert remember_note(text) is None


def test_write_explicit_note_creates_only_a_tenant_memory_item(db):
    company = _company(db)
    item = MemoryService().write_explicit_note(db, "prefiero largo plazo", company, "company")
    assert item.source_type == "chat" and item.memory_type == "chat_memory"
    assert item.company_id == company.id and item.scope == "company"
    assert item.metadata_ == {"write_policy": "explicit_remember_instruction"}
    assert [m.content for m in db.query(MemoryItem).all()] == ["prefiero largo plazo"]
    general = MemoryService().write_explicit_note(db, "nota general", None, "portfolio")
    assert general.company_id is None and general.scope == "portfolio"
