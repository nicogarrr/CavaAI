"""La sesion de BD no se toca mientras se descargan filings (F370).

Antes, persistir cada filing nada mas descargarlo dejaba una transaccion abierta
(conexion del pool retenida) durante las descargas lentas de los siguientes y,
con varias peticiones a la vez, agotaba el pool y el backend devolvia 503.
"""

from app.services import insider_persistence, insider_service

XML = """<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport><value>2024-03-15</value></periodOfReport>
  <issuer><issuerCik>0001234567</issuerCik><issuerName>ACME</issuerName>
    <issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>1</rptOwnerCik>
    <rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer>
    <officerTitle><value>Chief Executive Officer</value></officerTitle>
    </reportingOwnerRelationship></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <securityTitle><value>Common Stock</value></securityTitle>
    <transactionDate><value>2024-03-10</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>1000</value></transactionShares>
      <transactionPricePerShare><value>10</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""

FILINGS = [
    {"accession_number": f"0001-24-00000{i}", "document_url": f"https://x/{i}.xml",
     "filing_date": "2024-03-15", "form": "4"}
    for i in range(4)
]


def _run(monkeypatch, fetcher):
    timeline: list[str] = []
    monkeypatch.setattr(insider_service, "_cik_for_ticker", lambda t, c: "0001234567")
    monkeypatch.setattr(
        insider_service.form4_connector, "recent_form4_filings",
        lambda cik, limit=20, client=None: list(FILINGS),
    )
    monkeypatch.setattr(
        insider_persistence, "persist_filing",
        lambda db, filing, parsed, **kw: timeline.append("db"),
    )
    monkeypatch.setattr(
        insider_service, "_persisted_filing_transactions",
        lambda *a, **k: timeline.append("db") or None,
    )

    def wrapped(filing):
        timeline.append("net")
        return fetcher(filing)

    result = insider_service.get_signals_for_ticker(
        "ACME", fetcher=wrapped, db=object(), tenant_id=1
    )
    return result, timeline


def test_db_untouched_until_all_downloads_finish(monkeypatch):
    result, timeline = _run(monkeypatch, lambda f: XML)
    assert timeline.count("net") == len(FILINGS)
    assert timeline.count("db") == len(FILINGS)
    last_net = max(i for i, e in enumerate(timeline) if e == "net")
    first_db = min(i for i, e in enumerate(timeline) if e == "db")
    assert last_net < first_db, timeline
    assert result["status"] == "ok"
    assert result["filings_parsed"] == len(FILINGS)


def test_failed_downloads_use_db_only_after_network_phase(monkeypatch):
    def flaky(filing):
        if filing["accession_number"].endswith(("1", "3")):
            raise RuntimeError("sec timeout")
        return XML

    result, timeline = _run(monkeypatch, flaky)
    last_net = max(i for i, e in enumerate(timeline) if e == "net")
    first_db = min(i for i, e in enumerate(timeline) if e == "db")
    assert last_net < first_db, timeline
    assert result["status"] == "partial"
    assert result["filings_failed"] == 2


def test_initial_tenant_lookup_connection_is_released_before_fetch(monkeypatch, tmp_path):
    """Sesion real + lookup previo (como get_db) + pool de tamano 1 (F370).

    Durante cada descarga no debe haber ninguna conexion fuera del pool, y el
    scope de tenant de db.info se conserva.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    engine = create_engine(
        f"sqlite:///{tmp_path / 'p.db'}",
        poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=1,
        connect_args={"check_same_thread": False},
    )
    db = sessionmaker(bind=engine)()
    db.info["tenant_id"] = 7
    db.execute(text("select 1"))  # lookup de tenant de get_db: abre transaccion
    assert engine.pool.checkedout() == 1

    monkeypatch.setattr(insider_service, "_cik_for_ticker", lambda t, c: "0001234567")
    monkeypatch.setattr(
        insider_service.form4_connector, "recent_form4_filings",
        lambda cik, limit=20, client=None: list(FILINGS),
    )
    monkeypatch.setattr(insider_persistence, "persist_filing", lambda *a, **k: None)
    monkeypatch.setattr(
        insider_service, "_persisted_filing_transactions", lambda *a, **k: None
    )
    held: list[int] = []

    def fetcher(filing):
        held.append(engine.pool.checkedout())
        return XML

    result = insider_service.get_signals_for_ticker(
        "ACME", fetcher=fetcher, db=db, tenant_id=7
    )
    assert held == [0] * len(FILINGS), held
    assert db.info["tenant_id"] == 7
    assert result["status"] == "ok"
    db.execute(text("select 1"))  # la sesion sigue usable
    db.close()
    engine.dispose()
