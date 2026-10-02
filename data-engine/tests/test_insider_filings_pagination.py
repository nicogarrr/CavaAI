"""Paginacion de /api/insider/filings: offset + total persistido."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import insider as insider_module
from app.core.database import get_db
from app.models.entities import Base, InsiderFiling, Tenant


def _client(n: int):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(engine)()
    db.add(Tenant(id=1, external_id="t"))
    for i in range(n):
        db.add(InsiderFiling(
            tenant_id=1, accession_number=f"0001234567-24-{i:06d}", form="4",
            issuer_cik="1234567", issuer_ticker="ACME",
            filing_date=f"2024-03-{(i % 28) + 1:02d}", parser_version="1.1",
        ))
    db.commit()
    app = FastAPI()
    app.include_router(insider_module.router, prefix="/api/insider")

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_offset_pages_cover_all_without_overlap_and_report_total():
    client = _client(7)
    pages = [
        client.get("/api/insider/filings", params={"ticker": "acme", "limit": 3, "offset": o}).json()
        for o in (0, 3, 6)
    ]
    assert [p["count"] for p in pages] == [3, 3, 1]
    assert {p["total"] for p in pages} == {7}
    accessions = [f["accession_number"] for p in pages for f in p["filings"]]
    assert len(set(accessions)) == 7


def test_negative_offset_rejected():
    client = _client(1)
    assert client.get("/api/insider/filings", params={"ticker": "ACME", "offset": -1}).status_code == 422
