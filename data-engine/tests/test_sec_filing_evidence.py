import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, Document, DocumentChunk
from app.services.sec_filing_evidence import (
    EvidenceError,
    parse_index,
    strip_sgml_wrapper,
    verify_entry,
)

_spec = importlib.util.spec_from_file_location(
    "ingest_sec_filings",
    Path(__file__).resolve().parent.parent / "scripts" / "ingest_sec_filings.py",
)
ingest_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest_mod)

CIK = "0001780312"
ACC = "0001193125-26-342540"
FOLDER = ACC.replace("-", "")
NAME = "doc.htm"
BODY = b"<html><body><p>Revenue was 31,520 thousand dollars in the quarter.</p>" + b"x" * 200 + b"</body></html>"
INDEX_HTML = f"""<div id="secNum"><strong>SEC Accession <acronym title="Number">No.</acronym></strong> {ACC} </div>
<div class="formContent"><div class="formGrouping"><div class="infoHead">Filing Date</div> <div class="info">2026-08-10</div>
<div class="infoHead">Documents</div> <div class="info">3</div></div><div class="formGrouping">
<div class="infoHead">Period of Report</div> <div class="info">2026-06-30</div></div></div>
<span class="companyName">X (Filer) CIK: <a href="/cgi-bin/browse-edgar?CIK={CIK}&amp;action=getcompany">{CIK}</a></span>
<table class="tableFile"><tr><th>Seq</th></tr><tr><td scope="row">1</td><td scope="row">8-K</td>
<td scope="row"><a href="/Archives/edgar/data/1780312/{FOLDER}/{NAME}">{NAME}</a></td><td scope="row">8-K</td>
<td scope="row">{len(BODY) - 7}</td></tr></table>"""


def _wrap(body: bytes) -> bytes:
    return (
        b"<DOCUMENT>\n<TYPE>8-K\n<SEQUENCE>1\n<FILENAME>" + NAME.encode()
        + b"\n<DESCRIPTION>8-K\n<TEXT>\n" + body + b"\n</TEXT>\n</DOCUMENT>\n"
    )


def _make(tmp_path, *, raw=None, index=INDEX_HTML, url=None, sha=None):
    raw = raw if raw is not None else _wrap(BODY)
    idx = index.encode()
    (tmp_path / "idx.htm").write_bytes(idx)
    (tmp_path / "f.htm").write_bytes(raw)
    return {
        "file": "f.htm",
        "index_file": "idx.htm",
        "url": url or f"https://www.sec.gov/Archives/edgar/data/1780312/{FOLDER}/{NAME}",
        "index_url": "https://www.sec.gov/idx",
        "index_sha256": hashlib.sha256(idx).hexdigest(),
        "sha256": sha or hashlib.sha256(raw).hexdigest(),
    }


def test_parse_index_reads_cik_accession_date_and_documents():
    index = parse_index(INDEX_HTML)
    assert (index.cik, index.accession) == (CIK, ACC)
    assert index.filing_date == date(2026, 8, 10)
    assert index.period == date(2026, 6, 30)
    assert index.documents[NAME][0] == "8-K"


def test_verified_entry_takes_date_from_index_not_manifest(tmp_path):
    entry = _make(tmp_path)
    entry["published_at"] = "2020-01-01"  # declarado por el operador: se ignora
    filing = verify_entry(entry, tmp_path, "1780312")
    assert filing.filing_date == date(2026, 8, 10)
    assert filing.body == BODY
    assert filing.size_delta == 7


def test_wrong_company_cik_is_rejected(tmp_path):
    with pytest.raises(EvidenceError, match="CIK"):
        verify_entry(_make(tmp_path), tmp_path, "1234567")
    with pytest.raises(EvidenceError, match="CIK"):
        verify_entry(_make(tmp_path), tmp_path, None)


def test_tampered_index_or_document_is_rejected(tmp_path):
    entry = _make(tmp_path)
    (tmp_path / "idx.htm").write_bytes(INDEX_HTML.replace("2026-08-10", "2026-08-11").encode())
    with pytest.raises(EvidenceError, match="index_sha256"):
        verify_entry(entry, tmp_path, "1780312")
    entry = _make(tmp_path, sha="0" * 64)
    with pytest.raises(EvidenceError, match="sha256"):
        verify_entry(entry, tmp_path, "1780312")


def test_url_must_hang_from_index_accession_and_be_listed(tmp_path):
    other = "https://www.sec.gov/Archives/edgar/data/1780312/000119312526000001/doc.htm"
    with pytest.raises(EvidenceError, match="accession"):
        verify_entry(_make(tmp_path, url=other), tmp_path, "1780312")
    unlisted = f"https://www.sec.gov/Archives/edgar/data/1780312/{FOLDER}/other.htm"
    with pytest.raises(EvidenceError, match="no lista"):
        verify_entry(_make(tmp_path, url=unlisted), tmp_path, "1780312")
    evil = f"https://evil.example/Archives/edgar/data/1780312/{FOLDER}/{NAME}"
    with pytest.raises(EvidenceError, match="sec.gov"):
        verify_entry(_make(tmp_path, url=evil), tmp_path, "1780312")


def test_size_far_from_index_is_rejected(tmp_path):
    big = _wrap(BODY + b"y" * 1000)
    with pytest.raises(EvidenceError, match="incoherente"):
        verify_entry(_make(tmp_path, raw=big), tmp_path, "1780312")


def test_strip_wrapper_roundtrip_and_unwrapped_passthrough():
    body, doc_type, name = strip_sgml_wrapper(_wrap(BODY))
    assert (body, doc_type, name) == (BODY, "8-K", NAME)
    assert strip_sgml_wrapper(BODY) == (BODY, None, None)


@pytest.fixture
def company():
    init_db()
    with SessionLocal() as db:
        row = Company(
            ticker="TSTSEC", name="Test SEC Co", exchange="NASDAQ", currency="USD",
            sector="Tech", industry="Tech", company_type="holding", valuation_model="unassigned",
            special_sources=[], special_risks=[], factor_tags=[], cik="1780312",
        )
        db.add(row)
        db.commit()
        company_id = row.id
    yield company_id
    with SessionLocal() as db:
        doc_ids = db.scalars(select(Document.id).where(Document.company_id == company_id)).all()
        if doc_ids:
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids)))
            db.execute(delete(Document).where(Document.id.in_(doc_ids)))
        db.execute(delete(Company).where(Company.id == company_id))
        db.commit()


def test_ingest_dry_run_idempotency_and_rejection(tmp_path, company, monkeypatch):
    monkeypatch.setattr(
        ingest_mod.DocumentStore, "put_bytes", lambda self, *a, **k: "memory://test"
    )
    entry = _make(tmp_path)
    bad = dict(entry, sha256="0" * 64)
    with SessionLocal() as db:
        row = db.get(Company, company)
        dry = ingest_mod.ingest_filings(db, row, [entry], tmp_path, dry_run=True)
        assert dry[0]["status"] == "dry_run"
        assert db.scalar(select(Document).where(Document.company_id == company)) is None

        first = ingest_mod.ingest_filings(db, row, [entry, bad], tmp_path, dry_run=False)
        assert [r["status"] for r in first] == ["ingested", "rejected"]
        again = ingest_mod.ingest_filings(db, row, [entry], tmp_path, dry_run=False)
        assert again[0]["status"] == "duplicate"

        docs = db.scalars(select(Document).where(Document.company_id == company)).all()
        assert len(docs) == 1
        doc = docs[0]
        assert doc.source_type == "primary_official"
        assert doc.published_at.date() == date(2026, 8, 10)
        assert doc.metadata_["date_source"] == "sec_filing_index"
        assert doc.metadata_["cik"] == CIK and doc.metadata_["accession"] == ACC
        assert doc.metadata_["size_delta_vs_index"] == 7
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc.id)).all()
        assert chunks and "31,520" in " ".join(c.text for c in chunks)
    json.dumps(first)  # resultados serializables
