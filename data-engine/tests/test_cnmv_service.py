"""S1b: CNMV OIR service — mapped/unmapped/degraded behaviors, provenance."""

from pathlib import Path

import httpx
import pytest

from app.services import cnmv_service
from app.services.connectors import cnmv

FIXTURE = Path(__file__).parent / "fixtures" / "cnmv_oir_results.html"


def _fixture_client(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")

    class _Resp:
        def raise_for_status(self): pass
        text = html

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None): return _Resp()
        async def aclose(self): pass

    monkeypatch.setattr(cnmv.httpx, "AsyncClient", _Client)


def test_unmapped_ticker_is_unavailable_never_guessed():
    result = cnmv_service.get_oir_for_ticker("AAPL")
    assert result["status"] == "unavailable"
    assert result["filings"] == []
    assert "never guessed" in result["reason"]


def test_mapped_ticker_filters_by_nif(monkeypatch):
    _fixture_client(monkeypatch)
    # Viscofan esta en la tabla revisada (tanda 1, 2026-09-25, verificada
    # contra datosentidad + ancv/isin de CNMV).
    result = cnmv_service.get_oir_for_ticker("VIS")
    assert result["status"] == "ok"
    assert result["legal_name"] == "VISCOFAN, S.A."
    assert len(result["filings"]) == 1
    filing = result["filings"][0]
    assert filing["ticker"] == "VIS"
    assert filing["document_url"].startswith("https://www.cnmv.es/")
    assert result["provenance"]["source_kind"] == "official"
    assert result["provenance"]["coverage"] == "ok"


def test_mapped_ticker_without_filings_is_explicit(monkeypatch):
    _fixture_client(monkeypatch)
    # ITX is reviewed but has no filings in the fixture -> honest unavailable coverage
    result = cnmv_service.get_oir_for_ticker("ITX")
    assert result["status"] == "ok"
    assert result["filings"] == []
    assert result["provenance"]["coverage"] == "unavailable"


def test_http_failure_degrades_honestly(monkeypatch):
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None): raise httpx.ConnectTimeout("slow")
        async def aclose(self): pass

    monkeypatch.setattr(cnmv.httpx, "AsyncClient", _Client)
    result = cnmv_service.get_oir_for_ticker("ITX")
    assert result["status"] == "degraded"
    assert "ConnectTimeout" in result["reason"]
    assert result["filings"] == []


def test_structure_drift_degrades_honestly(monkeypatch):
    class _Resp:
        def raise_for_status(self): pass
        text = "<html><body>new design</body></html>"

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None): return _Resp()
        async def aclose(self): pass

    monkeypatch.setattr(cnmv.httpx, "AsyncClient", _Client)
    result = cnmv_service.get_oir_for_ticker("ITX")
    assert result["status"] == "degraded"
    assert "structure changed" in result["reason"]
