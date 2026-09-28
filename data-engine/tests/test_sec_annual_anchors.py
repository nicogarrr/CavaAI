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

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return payload

    class _MirrorClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            llamadas["url"] = url
            return _Resp()

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _MirrorClient)

    class _H:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            if "sec.gov" in url:
                class R403:
                    status_code = 403
                    headers = {}
                    def raise_for_status(self):
                        import httpx as _httpx
                        raise _httpx.HTTPStatusError("403", request=None, response=None)
                    def json(self): return {}
                return R403()
            llamadas["url"] = url
            return _Resp()

    monkeypatch.setattr(sec_edgar.httpx, "AsyncClient", _H)
    data = asyncio.run(sec_edgar._get_json(
        "https://data.sec.gov/submissions/CIK0000000001.json"))
    assert data == payload
    assert llamadas["url"].endswith(
        "/datasets/nico/cavaai-sec-mirror/resolve/main/submissions/CIK0000000001.json")
    get_settings.cache_clear()
