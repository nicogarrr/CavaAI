from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, NewsEvent, Tenant
from app.services.primary_claim_verifier import AtomicClaim, verify_itu_claims
from app.services.primary_source_ingestion import ingest_explicit_primary_source

FIXTURE = Path(__file__).parent / "fixtures" / "itu" / "d2026-84958-detail.html"
URL = "https://www.itu.int/ITU-R/space/asreceived/Publication/DisplayPublication/72184"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        a, b = Tenant(external_id="verify-A", name="A"), Tenant(external_id="verify-B", name="B")
        company = Company(ticker="ASTS", name="AST", exchange="NASDAQ", currency="USD",
                          company_type="holding", valuation_model="unassigned")
        session.add_all([a, b, company])
        session.flush()
        news = NewsEvent(tenant_id=a.id, company_id=company.id, source="Publisher",
                         title="Processed summary", url="https://publisher.example/news",
                         metadata_={"source_headline": "Total number of satellites: 344"})
        session.add(news)
        session.commit()
        session.info["tenant_id"] = a.id
        yield session, a, b, news
    engine.dispose()


def test_no_document_or_broad_approval_claim_never_verified(db, monkeypatch):
    session, a, b, news = db
    direct = AtomicClaim("NumberOfSatellites", "344", "Total number of satellites: 344")
    assert verify_itu_claims(session, news_event_id=news.id, claims=[direct])[0]["status"] == "not_verifiable"
    from app.services import primary_source_ingestion as module
    from app.services.document_store import DocumentStore
    monkeypatch.setattr(module, "fetch_public_url", lambda *args, **kw: (FIXTURE.read_bytes(), "text/html", URL))
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kw: "test://fixture")
    ingest_explicit_primary_source(session, news_event_id=news.id, official_url=URL,
                                   reference_kind="official_registry")
    semantic = AtomicClaim("NumberOfSatellites", "344", "ITU approved 344 satellites")
    assert verify_itu_claims(session, news_event_id=news.id, claims=[semantic])[0]["status"] == "not_verifiable"
    result = verify_itu_claims(session, news_event_id=news.id, claims=[direct])[0]
    assert result["status"] == "supported"
    assert result["claim_citation"]["excerpt"] == direct.literal
    evidence = result["evidence"]
    assert evidence["source_url"] == URL and evidence["official_literal"] == direct.literal
    assert "NumberOfSatellites" in evidence["locator"] and len(evidence["checksum"]) == 64
    assert evidence["publication_date"] is None and evidence["registry_date"] == "2026-09-24"
    session.info["tenant_id"] = b.id
    with pytest.raises(LookupError):
        verify_itu_claims(session, news_event_id=news.id, claims=[direct])


def test_complete_field_can_contradict_exact_claim_but_not_arbitrary_text(db, monkeypatch):
    session, a, b, news = db
    from app.services import primary_source_ingestion as module
    from app.services.document_store import DocumentStore
    monkeypatch.setattr(module, "fetch_public_url", lambda *args, **kw: (FIXTURE.read_bytes(), "text/html", URL))
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kw: "test://fixture")
    ingest_explicit_primary_source(session, news_event_id=news.id, official_url=URL,
                                   reference_kind="official_registry")
    news.metadata_ = {"source_headline": "Total number of satellites: 345"}
    session.commit()
    result = verify_itu_claims(session, news_event_id=news.id,
                               claims=[AtomicClaim("NumberOfSatellites", "345", "Total number of satellites: 345")])[0]
    assert result["status"] == "contradicted"
    assert result["evidence"]["official_literal"] == "Total number of satellites: 344"
    assert verify_itu_claims(session, news_event_id=news.id,
                             claims=[AtomicClaim("NumberOfSatellites", "1344", "Total number of satellites: 1344")])[0]["status"] == "not_verifiable"


def test_mutated_chunk_text_with_stale_hash_fails_closed(db, monkeypatch):
    from sqlalchemy import select

    from app.models.entities import DocumentChunk
    from app.services import primary_source_ingestion as module
    from app.services.document_store import DocumentStore

    session, a, b, news = db
    monkeypatch.setattr(module, "fetch_public_url", lambda *args, **kw: (FIXTURE.read_bytes(), "text/html", URL))
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kw: "test://fixture")
    response = ingest_explicit_primary_source(session, news_event_id=news.id, official_url=URL,
                                               reference_kind="official_registry")
    # Change the decisive value without changing stored provenance/hash.
    chunks = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == response["document_id"])).all()
    target = next(c for c in chunks if "Total number of satellites: 344" in c.text)
    target.text = target.text.replace("Total number of satellites: 344", "Total number of satellites: 345")
    news.metadata_ = {"source_headline": "Total number of satellites: 345"}
    session.commit()
    result = verify_itu_claims(session, news_event_id=news.id,
                               claims=[AtomicClaim("NumberOfSatellites", "345", "Total number of satellites: 345")])[0]
    assert result["status"] == "not_verifiable" and result["evidence"] is None


def test_invalid_linked_revision_cannot_be_ignored_in_favor_of_valid_one(db, monkeypatch):
    from sqlalchemy import select

    from app.models.entities import PrimarySourceRecord
    from app.services import primary_source_ingestion as module
    from app.services.document_store import DocumentStore

    session, a, b, news = db
    monkeypatch.setattr(module, "fetch_public_url", lambda *args, **kw: (FIXTURE.read_bytes(), "text/html", URL))
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kw: "test://fixture")
    response = ingest_explicit_primary_source(session, news_event_id=news.id, official_url=URL,
                                               reference_kind="official_registry")
    record = session.scalar(select(PrimarySourceRecord).where(PrimarySourceRecord.id == response["record_id"]))
    session.add(PrimarySourceRecord(tenant_id=a.id, news_event_id=news.id, document_id=record.document_id,
                                    requested_url=URL, final_url=URL, checksum="0" * 64,
                                    fetched_at=record.fetched_at, reference_kind="official_registry"))
    session.commit()
    result = verify_itu_claims(session, news_event_id=news.id,
                               claims=[AtomicClaim("NumberOfSatellites", "344", "Total number of satellites: 344")])[0]
    assert result["status"] == "not_verifiable" and result["evidence"] is None
