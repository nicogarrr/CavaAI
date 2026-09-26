"""PR-2: persistencia durable e idempotente de Form 4/4-A."""

from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models.entities import InsiderFiling, InsiderTransaction
from app.services import insider_persistence
from app.services.connectors import form4 as form4_connector
from tests.test_insider_signals import CEO_BUY_XML

FILING = {
    "form": "4",
    "accession_number": "0001234567-24-000001",
    "filing_date": "2024-03-16",
    "report_date": "2024-03-15",
    "document_url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456724000001/f4.xml",
    "index_url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456724000001/",
}

AMENDMENT_FILING = {
    **FILING,
    "form": "4/A",
    "accession_number": "0001234567-24-000010",
    "filing_date": "2024-03-20",
    "document_url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456724000010/f4a.xml",
}


def _db():
    init_db()
    return SessionLocal()


def _cleanup(db):
    db.query(InsiderTransaction).delete()
    db.query(InsiderFiling).delete()
    db.commit()


def test_persist_filing_is_idempotent_and_keeps_provenance():
    db = _db()
    try:
        _cleanup(db)
        parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)

        first = insider_persistence.persist_filing(db, FILING, parsed, xml_text=CEO_BUY_XML)
        assert first["filing_created"] is True
        assert first["transactions_created"] == 1

        second = insider_persistence.persist_filing(db, FILING, parsed, xml_text=CEO_BUY_XML)
        assert second["filing_created"] is False
        assert second["transactions_created"] == 0

        filings = db.scalars(select(InsiderFiling)).all()
        assert len(filings) == 1
        record = filings[0]
        assert record.accession_number == FILING["accession_number"]
        assert record.form == "4"
        assert record.is_amendment is False
        assert record.source_url == FILING["document_url"]
        assert record.parser_version == insider_persistence.PARSER_VERSION
        assert record.raw_sha256 is not None

        rows = db.scalars(select(InsiderTransaction)).all()
        assert len(rows) == 1
        tx = rows[0]
        assert tx.code == "P"
        assert tx.acquired_disposed == "A"
        assert tx.insider == "DOE JANE"
        assert tx.value == 5000 * 250
        assert tx.source_url == FILING["document_url"]
        assert len(tx.fingerprint) == 64
    finally:
        _cleanup(db)
        db.close()


def test_amendment_creates_immutable_separate_filing():
    """Un 4/A nunca sobrescribe el filing original: dos filas inmutables."""
    db = _db()
    try:
        _cleanup(db)
        parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
        insider_persistence.persist_filing(db, FILING, parsed, xml_text=CEO_BUY_XML)
        insider_persistence.persist_filing(db, AMENDMENT_FILING, parsed, xml_text=CEO_BUY_XML)

        filings = {
            f.accession_number: f
            for f in db.scalars(select(InsiderFiling)).all()
        }
        assert set(filings) == {FILING["accession_number"], AMENDMENT_FILING["accession_number"]}
        original = filings[FILING["accession_number"]]
        amendment = filings[AMENDMENT_FILING["accession_number"]]
        assert original.form == "4" and original.is_amendment is False
        assert amendment.form == "4/A" and amendment.is_amendment is True
        # El original no fue mutado por la enmienda.
        assert original.filing_date == FILING["filing_date"]

        rows = db.scalars(select(InsiderTransaction)).all()
        # Una fila por filing: los fingerprints llevan el accession, no colisionan.
        assert len(rows) == 2
        assert {r.accession_number for r in rows} == set(filings)
    finally:
        _cleanup(db)
        db.close()


def test_fingerprint_is_stable_and_field_sensitive():
    parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
    tx = parsed["transactions"][0]
    fp1 = insider_persistence.transaction_fingerprint("ACC-1", 0, tx)
    fp2 = insider_persistence.transaction_fingerprint("ACC-1", 0, tx)
    assert fp1 == fp2
    changed = {**tx, "shares": 6000.0}
    assert insider_persistence.transaction_fingerprint("ACC-1", 0, changed) != fp1
    assert insider_persistence.transaction_fingerprint("ACC-2", 0, tx) != fp1


def test_get_signals_persists_best_effort(monkeypatch):
    """El pipeline persiste cuando recibe db y sigue funcionando si falla."""
    from app.services import insider_service

    monkeypatch.setattr(insider_service, "_cik_for_ticker", lambda t, client=None: "0001234567")
    monkeypatch.setattr(
        form4_connector, "recent_form4_filings", lambda cik, limit=20, client=None: [FILING]
    )

    db = _db()
    try:
        _cleanup(db)
        result = insider_service.get_signals_for_ticker(
            "ACME", fetcher=lambda f: CEO_BUY_XML, db=db
        )
        assert result["status"] == "ok"
        assert db.scalars(select(InsiderFiling)).all()
        assert db.scalars(select(InsiderTransaction)).all()

        # Una persistencia rota no rompe la lectura.
        _cleanup(db)
        def boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(insider_persistence, "persist_filing", boom)
        result = insider_service.get_signals_for_ticker(
            "ACME", fetcher=lambda f: CEO_BUY_XML, db=db
        )
        assert result["status"] == "ok"
        assert any("persist" in e for e in result.get("filing_errors", []))
    finally:
        _cleanup(db)
        db.close()
