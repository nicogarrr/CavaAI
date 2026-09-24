"""Modo snapshot EDGAR: la SEC bloquea IPs de datacenter, asi que el
conector debe leer snapshots locales (mismo formato JSON oficial) cuando
SEC_SNAPSHOT_DIR esta configurado, y caer a la red solo si falta el fichero."""

import asyncio
import json

import httpx

from app.services.connectors import sec_edgar


def _snapshot_dir(tmp_path, monkeypatch):
    (tmp_path / "companyfacts").mkdir()
    (tmp_path / "submissions").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps({"tickers": {"AAPL": "320193"}, "fetched_at": "2026-09-20"})
    )
    (tmp_path / "companyfacts" / "CIK0000320193.json").write_text(
        json.dumps({"entityName": "Apple Inc.", "facts": {"us-gaap": {}}})
    )
    monkeypatch.setenv("SEC_SNAPSHOT_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    return tmp_path


def test_cik_for_ticker_usa_manifest(tmp_path, monkeypatch):
    _snapshot_dir(tmp_path, monkeypatch)

    async def fail_get(*args, **kwargs):  # no debe llamar a la red
        raise AssertionError("network llamada")

    monkeypatch.setattr(sec_edgar, "_get_json", fail_get)
    assert asyncio.run(sec_edgar.cik_for_ticker("aapl")) == "0000320193"


def test_company_facts_lee_snapshot(tmp_path, monkeypatch):
    _snapshot_dir(tmp_path, monkeypatch)
    data = asyncio.run(sec_edgar.company_facts("320193"))
    assert data["entityName"] == "Apple Inc."


def test_url_desconocida_va_a_red(tmp_path, monkeypatch):
    _snapshot_dir(tmp_path, monkeypatch)
    assert sec_edgar._snapshot_path_for("https://otra-cosa.example/x") is None


def test_secclient_async_usa_manifest_y_snapshot(tmp_path, monkeypatch):
    """El SECClient async (ingesta financiera) tambien respeta el snapshot."""
    from app.services.connectors.sec import SECClient

    _snapshot_dir(tmp_path, monkeypatch)

    async def probe():
        async def fail_handler(request):  # pragma: no cover - no debe llamarse
            raise AssertionError("network llamada")

        transport = httpx.MockTransport(fail_handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = SECClient(client=http)
            assert await client.cik_for_ticker("AAPL") == "0000320193"
            facts = await client.company_facts("320193")
            assert facts["entityName"] == "Apple Inc."

    asyncio.run(probe())
