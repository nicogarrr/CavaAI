"""F353: SECClient.annual_report_anchors - la evidencia de calendario fiscal
a nivel de filing (submissions): fusiona recent + ficheros historicos, filtra
a filings anuales (10-K y variantes) y descarta ficheros que fallan con
cobertura parcial (nunca rompe la ingesta)."""

import asyncio

from app.services.connectors.sec import SECClient


def _subs(rows, files=None):
    recent = {"accessionNumber": [], "form": [], "reportDate": []}
    for accn, form, report in rows:
        recent["accessionNumber"].append(accn)
        recent["form"].append(form)
        recent["reportDate"].append(report)
    return {"filings": {"recent": recent, "files": files or []}}


class _FakeHTTPSEC(SECClient):
    def __init__(self, payloads):
        self._payloads = payloads  # {url-suffix: dict | Exception}

    async def _get_json(self, url):
        for suffix, payload in self._payloads.items():
            if url.endswith(suffix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"URL inesperada: {url}")


def test_fusiona_recent_e_historicos_y_filtra_formularios():
    main = _subs(
        [
            ("A1", "10-K", "2025-12-31"),
            ("A2", "10-Q", "2025-09-30"),   # trimestral: fuera
            ("A3", "8-K", ""),              # sin cierre: fuera
            ("A4", "10-K/A", "2024-12-31"), # enmienda: dentro
            ("A5", "20-F", "2023-12-31"),   # emisor extranjero: dentro
        ],
        files=[{"name": "CIK0000000001-submissions-001.json"}],
    )
    # Los ficheros historicos llevan las columnas en primer nivel (formato
    # real de la SEC), no bajo filings.recent.
    extra = _subs([("A6", "10-K", "2019-03-31"), ("A7", "S-1", "2019-01-01")])["filings"]["recent"]
    client = _FakeHTTPSEC({
        "CIK0000000001.json": main,
        "CIK0000000001-submissions-001.json": extra,
    })
    anchors = asyncio.run(client.annual_report_anchors("1"))
    assert anchors == {
        "A1": "2025-12-31",
        "A4": "2024-12-31",
        "A5": "2023-12-31",
        "A6": "2019-03-31",
    }


def test_fichero_historico_roto_es_cobertura_parcial_no_error():
    main = _subs(
        [("A1", "10-K", "2025-12-31")],
        files=[{"name": "CIK0000000001-submissions-001.json"}],
    )
    client = _FakeHTTPSEC({
        "CIK0000000001.json": main,
        "CIK0000000001-submissions-001.json": RuntimeError("SEC 403"),
    })
    assert asyncio.run(client.annual_report_anchors("1")) == {"A1": "2025-12-31"}


# --- Mirror HF como fallback de lectura (ban de IP de datacenter) ---

def test_fallback_a_mirror_hf_en_403(monkeypatch):
    from app.core.config import get_settings
    from app.services.connectors import sec_edgar

    get_settings.cache_clear()
    monkeypatch.setenv("SEC_HF_MIRROR_DATASET", "nico/cavaai-sec-mirror")
    get_settings.cache_clear()

    payload = {"filings": {"recent": {}}}
    llamadas = {}
    monkeypatch.setattr(sec_edgar, "_MANIFEST_CACHE", {})
    monkeypatch.setattr(sec_edgar, "_MIRROR_SERVES", [])

    class _Resp:
        def __init__(self, data, status=200):
            self._data = data
            self.status_code = status
            self.headers = {}
        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx as _httpx
                raise _httpx.HTTPStatusError(str(self.status_code), request=None, response=None)
        def json(self):
            return self._data

    class _H:
        """SEC directo da 403; el mirror sirve manifest fresco + documento."""
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            if "sec.gov" in url:
                return _Resp({}, status=403)
            if url.endswith("/manifest.json"):
                from datetime import UTC, datetime
                return _Resp({"tickers": {}, "synced_at": datetime.now(UTC).isoformat()})
            llamadas["url"] = url
            return _Resp(payload)

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _H)
    data = asyncio.run(sec_edgar._get_json(
        "https://data.sec.gov/submissions/CIK0000000001.json"))
    assert data == payload
    assert llamadas["url"].endswith(
        "/datasets/nico/cavaai-sec-mirror/resolve/main/submissions/CIK0000000001.json")
    get_settings.cache_clear()


# --- Fallback mirror por la ruta SECClient (la de la ingesta real) ---

def _mirror_env(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SEC_HF_MIRROR_DATASET", "nico/cavaai-sec-mirror")
    get_settings.cache_clear()
    return get_settings


def test_secclient_403_cae_al_mirror(monkeypatch):
    """La ruta de ingesta (SECClient._get_json: company_facts, submissions,
    annual_report_anchors) cae al mirror HF ante 403 directo."""
    from app.services.connectors import sec_edgar
    from app.services.connectors.sec import SECClient

    _mirror_env(monkeypatch)
    payload = {"cik": 1, "facts": {"us-gaap": {}}}
    llamadas = {}
    monkeypatch.setattr(sec_edgar, "_MANIFEST_CACHE", {})
    monkeypatch.setattr(sec_edgar, "_MIRROR_SERVES", [])

    class _Resp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
        def raise_for_status(self): pass
        def json(self): return self._data

    class _MirrorHTTP:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            if url.endswith("/manifest.json"):
                from datetime import UTC, datetime
                return _Resp({"tickers": {}, "synced_at": datetime.now(UTC).isoformat()})
            llamadas["url"] = url
            return _Resp(payload)

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _MirrorHTTP)

    client = SECClient()
    import httpx as _httpx

    async def _get_403(url):
        req = _httpx.Request("GET", url)
        resp = _httpx.Response(403, request=req)
        resp.raise_for_status()

    client._get = _get_403
    data = asyncio.run(client.company_facts("0000000001"))
    assert data == payload
    assert llamadas["url"].endswith(
        "/datasets/nico/cavaai-sec-mirror/resolve/main/companyfacts/CIK0000000001.json")
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_secclient_404_no_se_enmascara(monkeypatch):
    """Un 404 de la SEC es un fallo de dato: NO se consulta el mirror y el
    error original propaga."""
    from app.services.connectors import sec_edgar
    from app.services.connectors.sec import SECClient

    _mirror_env(monkeypatch)
    llamadas = {}

    class _MirrorHTTP:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            llamadas["url"] = url
            raise AssertionError("el mirror no debe consultarse ante un 404")

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _MirrorHTTP)

    client = SECClient()
    import httpx as _httpx

    async def _get_404(url):
        req = _httpx.Request("GET", url)
        resp = _httpx.Response(404, request=req)
        resp.raise_for_status()

    client._get = _get_404
    try:
        asyncio.run(client.company_facts("0000000001"))
        raise AssertionError("debio propagar el 404")
    except _httpx.HTTPStatusError:
        pass
    assert llamadas == {}
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_mirror_caducado_fail_closed(monkeypatch):
    """Manifest con synced_at > 48h: el mirror NO se sirve (dato viejo nunca
    como fresco); el error es claro."""
    from app.core.config import get_settings
    from app.services.connectors import sec_edgar

    get_settings.cache_clear()
    monkeypatch.setenv("SEC_HF_MIRROR_DATASET", "nico/cavaai-sec-mirror")
    get_settings.cache_clear()
    monkeypatch.setattr(sec_edgar, "_MANIFEST_CACHE", {})
    monkeypatch.setattr(sec_edgar, "_MIRROR_SERVES", [])

    class _Resp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
            self.headers = {}
        def raise_for_status(self): pass
        def json(self): return self._data

    class _StaleMirror:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            assert url.endswith("/manifest.json"), "no debe pedir el documento"
            return _Resp({"tickers": {}, "synced_at": "2026-09-20T00:00:00Z"})

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _StaleMirror)
    try:
        asyncio.run(sec_edgar.mirror_get_json(
            "https://data.sec.gov/submissions/CIK0000000001.json"))
        raise AssertionError("debio fallar cerrado")
    except RuntimeError as e:
        assert "caducado" in str(e)
    get_settings.cache_clear()


def test_mirror_sin_synced_at_fail_closed(monkeypatch):
    """Manifest sin synced_at valido: fail closed igualmente."""
    from app.core.config import get_settings
    from app.services.connectors import sec_edgar

    get_settings.cache_clear()
    monkeypatch.setenv("SEC_HF_MIRROR_DATASET", "nico/cavaai-sec-mirror")
    get_settings.cache_clear()
    monkeypatch.setattr(sec_edgar, "_MANIFEST_CACHE", {})
    monkeypatch.setattr(sec_edgar, "_MIRROR_SERVES", [])

    class _Resp:
        status_code = 200
        headers = {}
        def raise_for_status(self): pass
        def json(self): return {"tickers": {}}

    class _NoDate:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            return _Resp()

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _NoDate)
    try:
        asyncio.run(sec_edgar.mirror_get_json(
            "https://data.sec.gov/submissions/CIK0000000001.json"))
        raise AssertionError("debio fallar cerrado")
    except RuntimeError as e:
        assert "synced_at" in str(e)
    get_settings.cache_clear()
