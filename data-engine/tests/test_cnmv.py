"""S1a: CNMV connector — real-fixture parser contract + reviewed mapping rules."""

from pathlib import Path

import pytest

from app.services.cnmv_mapping import issuer_for_nif, resolve_issuer
from app.services.connectors.cnmv import CNMVParseError, parse_oir_results

FIXTURE = Path(__file__).parent / "fixtures" / "cnmv_oir_results.html"


def test_parse_real_oir_fixture():
    filings = parse_oir_results(FIXTURE.read_text(encoding="utf-8"))
    assert len(filings) == 3
    first = filings[0]
    assert first["entity_name"] == "VISCOFAN, S.A."
    assert first["nif"] == "A-31065501"
    assert first["category"] == "Programas de recompra de acciones, estabilización y autocartera"
    assert "recompra de 14 a 18 de septiembre" in first["title"]
    assert first["document_url"].startswith("https://www.cnmv.es/webservices/verdocumento/ver")
    assert first["registration_number"] == "42848"
    assert first["published_at"].startswith("2026-09-22T")
    assert "+02:00" in first["published_at"]  # Europe/Madrid DST
    assert all(f["entity_url"].startswith("https://www.cnmv.es/") for f in filings)


def test_parse_drift_raises_honestly():
    with pytest.raises(CNMVParseError):
        parse_oir_results("<html><body><p>CNMV rediseñó su web</p></body></html>")
    with pytest.raises(CNMVParseError):
        parse_oir_results("")


def test_mapping_exact_forms_resolve():
    assert resolve_issuer("ITX").nif == "A-15075062"
    assert resolve_issuer("itx.mc").ticker == "ITX"
    assert resolve_issuer("ES0148396007").ticker == "ITX"
    assert resolve_issuer("A-15075062").ticker == "ITX"
    assert resolve_issuer("A15075062").ticker == "ITX"  # NIF without dash
    assert resolve_issuer("INDUSTRIA DE DISEÑO TEXTIL, S.A.").ticker == "ITX"
    assert resolve_issuer("inditex").ticker == "ITX"  # reviewed alias


def test_mapping_unknown_is_unavailable_not_guessed():
    assert resolve_issuer("") is None
    assert resolve_issuer("IND") is None            # partial legal name: no guessing
    assert resolve_issuer("ABENGOA") is None         # not reviewed yet
    assert resolve_issuer("AAPL") is None           # US ticker: out of scope
    assert resolve_issuer("  ") is None


def test_mapping_table_integrity():
    from app.services.cnmv_mapping import REVIEWED_ISSUERS

    tickers = [i.ticker for i in REVIEWED_ISSUERS]
    nifs = [i.nif for i in REVIEWED_ISSUERS]
    isins = [i.isin for i in REVIEWED_ISSUERS]
    assert len(tickers) == len(set(tickers))
    assert len(nifs) == len(set(nifs))
    assert len(isins) == len(set(isins))
    assert all(i.isin.startswith("ES") for i in REVIEWED_ISSUERS)
    assert issuer_for_nif("a48010611").ticker == "IBE"
    assert issuer_for_nif("X-00000000") is None
