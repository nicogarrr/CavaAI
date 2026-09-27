"""F252: el mismo documento no se ingesta ni se lista dos veces.

La identidad estable de un documento descargado es (company_id, source_url):
SEC sirve el mismo filing con bytes que varian entre dias y el checksum no
lo capturaba, asi que cada re-ingesta creaba otra fila y las vistas listaban
tarjetas duplicadas (ASML 34/17, AAPL 40/20, /research/sources 50/26).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.sources import documents, documents_count
from app.models.entities import Base, Company, Document
from app.services.company_events_service import CompanyEventsService
from app.services.document_ingestion_service import DocumentIngestionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", cik="0000320193", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _doc(db: Session, company: Company, url: str | None, title: str, day: int) -> Document:
    doc = Document(
        company_id=company.id, title=title, source_type="SEC", source_url=url,
        published_at=datetime(2026, 9, day, tzinfo=UTC), checksum=f"sum-{url}-{day}-{title}",
        metadata_={}, tenant_id="tenant-test",
    )
    db.add(doc)
    return doc


def test_ingest_bytes_dedupes_by_source_url_despite_byte_drift(db):
    """Mismo filing, bytes ligeramente distintos (deriva diaria de SEC):
    la segunda ingesta es duplicado, no una fila nueva."""
    _company(db)
    service = DocumentIngestionService()
    url = "https://www.sec.gov/Archives/edgar/data/320193/0001/aapl-20250329.htm"
    text = b"AAPL 10-Q content with enough text to parse into blocks. " * 4

    first = service.ingest_bytes(
        db, ticker="AAPL", title="AAPL 10-Q (2025-03-29)", content=text,
        filename="aapl-20250329.htm", source_type="SEC", source_url=url,
    )
    assert first["status"] == "ingested"

    second = service.ingest_bytes(
        db, ticker="AAPL", title="AAPL 10-Q (2025-03-29)", content=text + b" ",
        filename="aapl-20250329.htm", source_type="SEC", source_url=url,
    )
    assert second["status"] == "duplicate"
    count = db.scalar(select(Document).where(Document.source_url == url))
    assert count is not None
    assert len(db.scalars(select(Document).where(Document.source_url == url)).all()) == 1


def test_db_documents_dedupes_by_url_and_title(db):
    """La vista por empresa nunca lista dos tarjetas del mismo documento:
    dedupe por source_url (la mas reciente gana) y por titulo sin URL."""
    company = _company(db)
    url = "https://www.sec.gov/Archives/edgar/data/320193/0001/aapl-20250329.htm"
    _doc(db, company, url, "AAPL 10-Q (2025-03-29)", 26)
    _doc(db, company, url, "AAPL 10-Q (2025-03-29)", 27)
    _doc(db, company, "https://www.sec.gov/Archives/edgar/data/320193/0002/aapl-8k.htm", "AAPL 8-K", 25)
    _doc(db, company, None, "Nota interna", 24)
    _doc(db, company, None, "Nota interna", 23)
    db.commit()

    docs = CompanyEventsService(db)._db_documents(company, 40)
    assert [d["url"] for d in docs].count(url) == 1
    assert [d["title"] for d in docs].count("Nota interna") == 1
    assert len(docs) == 3
    # La mas reciente del par duplicado es la que se conserva.
    kept = next(d for d in docs if d["url"] == url)
    assert kept["published_at"].startswith("2026-09-27")


def test_global_documents_and_count_dedupe_by_url(db):
    """La vista global /research/sources y su contador excluyen las
    re-ingestas (misma company+URL); los documentos sin URL pasan todos."""
    company = _company(db)
    url = "https://www.sec.gov/Archives/edgar/data/320193/0001/aapl-20250329.htm"
    _doc(db, company, url, "AAPL 10-Q (2025-03-29)", 26)
    _doc(db, company, url, "AAPL 10-Q (2025-03-29)", 27)
    _doc(db, company, None, "FMP normalized financials - AAPL", 25)
    _doc(db, company, None, "SEC XBRL facts - AAPL", 24)
    db.commit()

    rows = documents(
        ticker=None, include_chunks=False, page=1, page_size=50,
        chunk_limit=1000, chunk_text_limit=1500, db=db,
    )
    urls = [row["source_url"] for row in rows]
    assert urls.count(url) == 1
    assert len(rows) == 3

    total = documents_count(ticker=None, db=db)
    assert total["total"] == 3
