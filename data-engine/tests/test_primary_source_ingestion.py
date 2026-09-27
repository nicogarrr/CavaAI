import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, Document, DocumentChunk, NewsEvent, PrimarySourceRecord, Tenant
from app.services.primary_source_ingestion import ingest_explicit_primary_source


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        tenants = [Tenant(external_id=f"primary-{i}", name=f"Tenant {i}") for i in (1, 2)]
        company = Company(ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD",
                          company_type="holding", valuation_model="unassigned")
        session.add_all([*tenants, company])
        session.flush()
        events = [NewsEvent(tenant_id=t.id, company_id=company.id, title="Publisher article",
                            url=f"https://publisher.example/{t.id}", source="Publisher") for t in tenants]
        session.add_all(events)
        session.commit()
        session.info["tenant_id"] = tenants[0].id
        yield session, tenants, events
    engine.dispose()


def test_requires_separately_supplied_official_url_and_tenant(db, monkeypatch):
    session, tenants, events = db
    assert ingest_explicit_primary_source(session, news_event_id=events[0].id,
                                          official_url=None, reference_kind="official_registry")["primary_status"] == "not_found"
    with pytest.raises(ValueError):
        ingest_explicit_primary_source(session, news_event_id=events[0].id,
                                       official_url=events[0].url, reference_kind="official_registry")
    with pytest.raises(ValueError):
        ingest_explicit_primary_source(session, news_event_id=events[1].id,
                                       official_url="https://www.itu.int/record", reference_kind="official_registry")
    assert session.scalars(select(PrimarySourceRecord)).all() == []


def test_html_unknown_date_dedup_hash_versions_and_no_auto_scans(db, monkeypatch):
    session, tenants, events = db
    from app.services import primary_source_ingestion as module
    from app.services.document_ingestion_service import DocumentIngestionService
    from app.services.document_store import DocumentStore

    bytes_now = [b"<html><body>ITU registration record D-BLUEBIRD with official orbital parameters.</body></html>"]
    monkeypatch.setattr(module, "fetch_public_url", lambda *args, **kwargs: (bytes_now[0], "text/html; charset=utf-8", "https://www.itu.int/record"))
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kwargs: "test://original")
    monkeypatch.setattr(DocumentIngestionService, "_jev_doc_type_meta", lambda *args: pytest.fail("unexpected classification"))
    kwargs = dict(news_event_id=events[0].id, official_url="https://www.itu.int/record",
                  reference_kind="official_registry")
    first = ingest_explicit_primary_source(session, **kwargs)
    assert first["status"] == "ingested" and first["published_at"] is None
    document = session.get(Document, first["document_id"])
    assert document.published_at is None and document.metadata_["date_source"] == "unknown"
    assert document.metadata_["requested_url"] == "https://www.itu.int/record"
    assert document.metadata_["byte_count"] == len(bytes_now[0])
    chunk = session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
    assert "D-BLUEBIRD" in chunk.text and chunk.metadata_["source_url"] == "https://www.itu.int/record"
    again = ingest_explicit_primary_source(session, **kwargs)
    assert again["status"] == "duplicate" and again["document_id"] == document.id
    bytes_now[0] = b"<html><body>ITU updated registration record D-BLUEBIRD with new parameters.</body></html>"
    changed = ingest_explicit_primary_source(session, **kwargs)
    assert changed["document_id"] != document.id
    assert len(session.scalars(select(PrimarySourceRecord)).all()) == 2


def test_redirect_mime_parser_fail_closed(db, monkeypatch):
    session, _, events = db
    from app.services import primary_source_ingestion as module
    from app.services.document_store import DocumentStore
    monkeypatch.setattr(DocumentStore, "put_bytes", lambda *args, **kwargs: "test://original")
    kwargs = dict(news_event_id=events[0].id, official_url="https://www.itu.int/record",
                  reference_kind="official_registry")
    for payload in [
        (b"Official data for filing ITU D-BLUEBIRD", "text/html", "https://publisher.example/article"),
        (b"Not a PDF but otherwise long enough", "application/pdf", "https://www.itu.int/record"),
        (b"short", "text/html", "https://www.itu.int/record"),
        (b"Official data for filing ITU D-BLUEBIRD", "application/octet-stream", "https://www.itu.int/record"),
    ]:
        monkeypatch.setattr(module, "fetch_public_url", lambda *args, payload=payload, **kw: payload)
        with pytest.raises(ValueError):
            ingest_explicit_primary_source(session, **kwargs)
    assert session.scalars(select(PrimarySourceRecord)).all() == []



def test_intermediate_redirect_to_nonofficial_host_rejected_before_fetch(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    import httpx

    from app.services import public_fetch

    visited = []
    def resolve(url):
        visited.append(url)
        return SimpleNamespace(url=url, request_url=url, host_header="www.itu.int", sni_hostname="www.itu.int")

    @contextmanager
    def stream(method, url, **kwargs):
        if url == "https://www.itu.int/start":
            yield SimpleNamespace(status_code=302, headers={"location": "https://publisher.example/bridge"})
        else:
            pytest.fail("Nonofficial intermediate redirect was fetched")

    class Client:
        def stream(self, method, url, **kwargs):
            return stream(method, url, **kwargs)

        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None

    monkeypatch.setattr(public_fetch, "_resolve_public_url", resolve)
    monkeypatch.setattr(public_fetch, "_connect_pinned_httpcore", lambda **kw: None)
    monkeypatch.setattr(httpx, "Client", lambda **kw: Client())
    with pytest.raises(ValueError, match="redirect denied"):
        public_fetch.fetch_public_url("https://www.itu.int/start", allowed_url=lambda url: url.startswith("https://www.itu.int/"))
    assert visited == ["https://www.itu.int/start"]
