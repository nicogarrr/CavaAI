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
