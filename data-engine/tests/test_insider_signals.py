"""Senales insider (Form 4 EDGAR): tests hermeticos, sin red.

- Parse de XML Form 4 de ejemplo (mock): ticker, insider, rol, P/S,
  acciones, precio, valor.
- Deteccion: cluster_buy (>=3 insiders / 30 dias), c_suite_buy (CEO/CFO),
  big_buy (>$1M).
- Endpoint GET /api/insider/signals con EDGAR mockeado.
- Enganche Telegram: apagado por defecto y nunca rompe.
"""

from fastapi.testclient import TestClient

import main
from app.services import insider_service
from app.services.connectors import form4 as form4_connector

CEO_BUY_XML = """<ownershipDocument>
  <schemaVersion>X0306</schemaVersion>
  <documentType>4</documentType>
  <periodOfReport><value>2024-03-15</value></periodOfReport>
  <issuer>
    <issuerCik>0001234567</issuerCik>
    <issuerName>ACME Corp</issuerName>
    <issuerTradingSymbol>ACME</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001111111</rptOwnerCik>
      <rptOwnerName>DOE JANE</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle><value>Chief Executive Officer</value></officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2024-03-10</value></transactionDate>
      <transactionCoding>
        <transactionCode><value>P</value></transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>250</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

SALE_XML = """<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport><value>2024-03-15</value></periodOfReport>
  <issuer>
    <issuerCik>0001234567</issuerCik>
    <issuerName>ACME Corp</issuerName>
    <issuerTradingSymbol>ACME</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0002222222</rptOwnerCik>
      <rptOwnerName>SMITH JOHN</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>0</isOfficer>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2024-03-11</value></transactionDate>
      <transactionCoding>
        <transactionCode><value>S</value></transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>260</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def _buy(insider, cik, title, day, value=100.0, shares=100.0):
    return {
        "ticker": "ACME",
        "insider": insider,
        "insider_cik": cik,
        "role": f"officer ({title})" if title else "director",
        "officer_title": title,
        "type": "P",
        "acquired_disposed": "A",
        "shares": shares,
        "price": value / shares,
        "value": value,
        "date": f"2024-03-{day:02d}",
    }


# ---------------- Parse ----------------


def test_form4_parse_extracts_ticker_insider_role_and_amounts():
    parsed = form4_connector.parse_form4_xml(CEO_BUY_XML)
    assert parsed["ticker"] == "ACME"
    assert parsed["issuer_name"] == "ACME Corp"
    assert len(parsed["transactions"]) == 1
    tx = parsed["transactions"][0]
    assert tx["insider"] == "DOE JANE"
    assert "Chief Executive Officer" in tx["role"]
    assert tx["type"] == "P"
    assert tx["shares"] == 5000
    assert tx["price"] == 250
    assert tx["value"] == 5000 * 250
    assert tx["date"] == "2024-03-10"


def test_form4_parse_rejects_non_ownership_document():
    import pytest

    with pytest.raises(ValueError):
        form4_connector.parse_form4_xml("<html></html>")


def test_open_market_buy_distinguishes_sale():
    buy = form4_connector.parse_form4_xml(CEO_BUY_XML)["transactions"][0]
    sale = form4_connector.parse_form4_xml(SALE_XML)["transactions"][0]
    assert form4_connector.is_open_market_buy(buy) is True
    assert form4_connector.is_open_market_buy(sale) is False
    assert insider_service.open_market_buys([buy, sale]) == [buy]


def test_sec_rate_limit_and_user_agent_contact():
    assert form4_connector.MIN_INTERVAL_SECONDS == 0.1  # 10 req/s
    assert "@" in form4_connector.resolve_user_agent()


# ---------------- Senales ----------------


def test_big_buy_over_one_million():
    txs = [_buy("DOE JANE", "0001111111", "Chief Executive Officer", 10, value=1_250_000.0)]
    signals = insider_service.detect_signals(txs)
    big = [s for s in signals if s["signal"] == "big_buy"]
    assert len(big) == 1
    assert big[0]["value"] == 1_250_000.0


def test_no_big_buy_below_threshold():
    txs = [_buy("DOE JANE", "0001111111", "Chief Executive Officer", 10, value=50_000.0)]
    assert [s for s in insider_service.detect_signals(txs) if s["signal"] == "big_buy"] == []


def test_c_suite_buy_ceo_and_cfo():
    txs = [
        _buy("DOE JANE", "0001111111", "Chief Executive Officer", 10),
        _buy("ROE RICH", "0003333333", "Chief Financial Officer", 11),
        _buy("SMITH JOHN", "0002222222", None, 12),  # director: no es c-suite
    ]
    c_suite = [s for s in insider_service.detect_signals(txs) if s["signal"] == "c_suite_buy"]
    assert {s["insider"] for s in c_suite} == {"DOE JANE", "ROE RICH"}


def test_cluster_buy_needs_three_insiders_in_30_days():
    txs = [
        _buy("A", "0000000001", None, 1),
        _buy("B", "0000000002", None, 10),
        _buy("C", "0000000003", None, 20),
    ]
    clusters = [s for s in insider_service.detect_signals(txs) if s["signal"] == "cluster_buy"]
    assert len(clusters) == 1
    assert clusters[0]["insider_count"] == 3
    assert clusters[0]["ticker"] == "ACME"

    two = txs[:2]  # solo 2 insiders -> sin cluster
    assert [s for s in insider_service.detect_signals(two) if s["signal"] == "cluster_buy"] == []

    spread = [
        _buy("A", "0000000001", None, 1),
        _buy("B", "0000000002", None, 1),
        _buy("C", "0000000003", None, 1),
    ]
    # Mismo insider 3 veces no es cluster (cuenta insiders distintos).
    same = [_buy("A", "0000000001", None, d) for d in (1, 2, 3)]
    assert spread and [s for s in insider_service.detect_signals(same) if s["signal"] == "cluster_buy"] == []


def test_sales_never_produce_buy_signals():
    sale = form4_connector.parse_form4_xml(SALE_XML)["transactions"][0]
    assert insider_service.detect_signals([sale]) == []


# ---------------- Enganche Telegram (nunca rompe) ----------------


def test_notify_skipped_when_flag_disabled(monkeypatch):
    monkeypatch.setenv("INSIDER_ALERTS_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        result = insider_service.maybe_notify_insider_buy(
            "ACME", [{"signal": "big_buy", "detail": "x"}]
        )
    finally:
        get_settings.cache_clear()
    assert result["status"] == "skipped"


def test_notify_never_raises_even_if_notifier_booms(monkeypatch):
    monkeypatch.setenv("INSIDER_ALERTS_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        def boom(_payload):
            raise RuntimeError("telegram caido")

        result = insider_service.maybe_notify_insider_buy(
            "ACME", [{"signal": "cluster_buy", "detail": "x"}], notifier=boom
        )
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert result["status"] == "skipped"


def test_notify_delivers_through_injected_notifier(monkeypatch):
    monkeypatch.setenv("INSIDER_ALERTS_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    seen = {}
    try:
        def fake(payload):
            seen["text"] = payload["message"]
            return {"status": "delivered"}

        result = insider_service.maybe_notify_insider_buy(
            "ACME",
            [{"signal": "c_suite_buy", "detail": "CEO DOE JANE compra en mercado abierto"}],
            notifier=fake,
        )
    finally:
        get_settings.cache_clear()
    assert result["status"] == "delivered"
    assert "insider buy" in seen["text"].lower()


# ---------------- Endpoint ----------------


def test_insider_signals_endpoint_with_mocked_edgar(monkeypatch):
    monkeypatch.setattr(
        insider_service, "_cik_for_ticker", lambda ticker, client=None: "0001234567"
    )
    monkeypatch.setattr(
        form4_connector,
        "recent_form4_filings",
        lambda cik, limit=20, client=None: [
            {
                "accession_number": "0001234567-24-000001",
                "filing_date": "2024-03-12",
                "document_url": "https://www.sec.gov/Archives/edgar/data/1234567/x.xml",
            }
        ],
    )
    monkeypatch.setattr(
        form4_connector, "fetch_filing_xml", lambda url, client=None: CEO_BUY_XML
    )

    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/api/insider/signals?ticker=ACME")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "ACME"
    assert payload["status"] == "ok"
    kinds = {s["signal"] for s in payload["signals"]}
    assert {"big_buy", "c_suite_buy"} <= kinds


def test_insider_signals_endpoint_degrades_without_network(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("red caida")

    monkeypatch.setattr(insider_service, "_cik_for_ticker", boom)
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/api/insider/signals?ticker=ACME")
    assert response.status_code == 200
    assert response.json()["signals"] == []
