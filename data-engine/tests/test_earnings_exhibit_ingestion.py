import asyncio

from app.services.feed_ingestion_service import FeedIngestionService

INDEX = '''Accession No. 0000000001-26-000001
<a href="?CIK=0000000001">CIK</a>
Filing Date</div><div class="info">2026-10-01</div>
Period of Report</div><div class="info">2026-09-30</div>
<a href="/Archives/edgar/data/1/000000000126000001/earnings.htm">earnings</a></td>
<td scope="row">EX-99.1</td><td scope="row">1234</td>
'''


class SEC:
    async def filing_document(self, url):
        return INDEX.encode(), "text/html"


def test_only_indexed_exhibits_and_parent_metadata(monkeypatch):
    service = FeedIngestionService(sec_client=SEC())
    ingested = []

    async def ingest(db, **kwargs):
        ingested.append(kwargs)
        return {"status": "ingested"}

    monkeypatch.setattr(service, "ingest_document_url", ingest)
    result = asyncio.run(service._earnings_exhibits(
        None, ticker="TEST", url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/main.htm",
        published_at=None, filing_metadata={"form": "8-K", "cik": "1", "accession_number": "0000000001-26-000001"},
    ))
    assert result == [{"status": "ingested"}]
    assert ingested[0]["url"].endswith("/earnings.htm")
    assert ingested[0]["filing_metadata"]["parent_form"] == "8-K"
    assert ingested[0]["filing_metadata"]["form"] == "EX-99.1"


def test_wrong_index_identity_is_not_ingested():
    service = FeedIngestionService(sec_client=SEC())
    result = asyncio.run(service._earnings_exhibits(
        None, ticker="TEST", url="https://www.sec.gov/Archives/edgar/data/2/000000000226000001/main.htm",
        published_at=None, filing_metadata={"form": "8-K", "cik": "2", "accession_number": "0000000002-26-000001"},
    ))
    assert result[0]["status"] == "unavailable"


def test_missing_sec_identity_is_honest():
    result = asyncio.run(FeedIngestionService()._earnings_exhibits(
        None, ticker="TEST", url="https://www.sec.gov/Archives/edgar/data/1/main.htm",
        published_at=None, filing_metadata={"form": "8-K"},
    ))
    assert result[0]["status"] == "insufficient_data"


def test_real_pool_released_for_index_and_multiple_exhibits(monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    from app.models.entities import Base, Company, Tenant, WatchItem
    from app.services.document_ingestion_service import DocumentIngestionService

    engine = create_engine("sqlite:///:memory:", poolclass=QueuePool, pool_size=1, max_overflow=0)
    Base.metadata.create_all(engine)
    checks = []
    multi_index = INDEX + INDEX[INDEX.index('<a href="/Archives'):].replace("earnings.htm", "other.htm").replace("EX-99.1", "EX-99.2")

    class PooledSEC:
        async def filing_document(self, url):
            checks.append((url, engine.pool.checkedout()))
            assert engine.pool.checkedout() == 0
            if url.endswith("-index.htm"):
                return multi_index.encode(), "text/html"
            return b"Quarterly results. Revenue was $4.87 billion.", "text/html"

    with sessionmaker(engine, expire_on_commit=False)() as db:
        tenant = Tenant(external_id="pool-b", name="Pool")
        db.add(tenant)
        db.commit()
        db.info["tenant_id"] = tenant.id
        db.add(Company(ticker="POOL", name="Pool", exchange="NASDAQ", currency="USD",
                       company_type="holding", valuation_model="unassigned"))
        db.commit()
        db.scalar(select(Company.id))  # prior read holds a connection
        db.add(WatchItem(symbol="POOL"))  # pending caller writes must survive

        def ingest(self, session, **kwargs):
            # Reproduce the optional scanner leaving a transaction open.
            session.scalar(select(Company.id))
            return {"status": "ingested"}

        monkeypatch.setattr(DocumentIngestionService, "ingest_bytes", ingest)
        result = asyncio.run(FeedIngestionService(sec_client=PooledSEC()).ingest_document_url(
            db, ticker="POOL", title="8-K", source_type="SEC",
            url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/main.htm",
            filing_metadata={"form": "8-K", "cik": "1", "accession_number": "0000000001-26-000001"},
        ))
        assert len(checks) == 4  # primary + index + two indexed exhibits
        assert all(count == 0 for _, count in checks)
        assert len(result["earnings_exhibits"]) == 2
        assert db.scalar(select(WatchItem.symbol)) == "POOL"
        assert db.info["tenant_id"] == tenant.id
    engine.dispose()
