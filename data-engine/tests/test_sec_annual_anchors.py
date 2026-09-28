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
