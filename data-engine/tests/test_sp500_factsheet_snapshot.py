"""Snapshot en disco del factsheet del S&P 500: modo offline, procedencia y parseo.

Cubre las tres piezas que sostienen la metrica en produccion sin red:

* el conector lee el snapshot de disco versionado y NO hace peticiones (la IP
  de la VM de OCI esta baneada por la SEC y aqui ni se pregunta a nadie);
* el manifest manda: sin sha256 declarado, o con sha256 que no casa, el
  snapshot no se sirve (fail closed ante una subida parcial);
* el builder es estricto: sin ancla, sin el numero de valores esperado, con
  fecha que no cuadra o con invariantes rotas, no escribe nada.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.services.connectors import sp500_factsheet
from app.services.connectors.sp500_factsheet import read_factsheet

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_sp500_factsheet_snapshots.py"


def _builder():
    spec = spec_from_file_location("build_sp500_factsheet_snapshots", SCRIPT)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Texto con la maqueta real de la pagina "Index Characteristics" del factsheet:
# las 8 etiquetas y despues los 7 valores, en este orden.
FACTSHEET_TEXT = """
Index Characteristics
[USD MILLION]
MEAN TOTAL MARKET CAP
LARGEST TOTAL MARKET CAP
SMALLEST TOTAL MARKET CAP
MEDIAN TOTAL MARKET CAP
NUMBER OF CONSTITUENTS
CONSTITUENT MARKET
WEIGHT LARGEST CONSTITUENT [%]
WEIGHT TOP 10 CONSTITUENTS [%]
503
136,835.41
5,347,407.51
5,858.44
44,734.65
8.1
37.8
AS OF AUGUST 31, 2026
FOR USE WITH INSTITUTIONS ONLY, NOT FOR USE WITH RETAIL INVESTORS.
"""


def _payload(as_of: str = "2026-08-31", **overrides) -> dict:
    payload = {
        "index": "S&P 500",
        "as_of": as_of,
        "synced_at": "2026-09-02T07:30:00+00:00",
        "source": "S&P 500 Index Factsheet (S&P Dow Jones Indices)",
        "source_url": "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
        "source_tier": "index_provider_official",
        "source_license": "descarga publica sin clave; solo agregados",
        "source_scope": "aggregate_index_characteristics_only",
        "metrics": {
            "constituents": 503,
            "weight_top_ten_pct": 37.8,
            "weight_largest_pct": 8.1,
            "mean_total_market_cap_usd_m": 136835.41,
            "largest_total_market_cap_usd_m": 5347407.51,
            "smallest_total_market_cap_usd_m": 5858.44,
            "median_total_market_cap_usd_m": 44734.65,
        },
    }
    payload.update(overrides)
    return payload


def _install(root: Path, payloads: list[dict], *, declare: bool = True, corrupt_sha: str | None = None) -> None:
    (root / "factsheets").mkdir(parents=True, exist_ok=True)
    manifest: dict = {"index": "S&P 500", "synced_at": "2026-09-02T07:30:00+00:00", "snapshots": {}}
    for payload in payloads:
        relative = f"factsheets/sp500-{payload['as_of']}.json"
        path = root / relative
        path.write_text(json.dumps(payload, indent=1, sort_keys=True))
        if not declare:
            continue
        manifest["snapshots"][relative] = {
            "as_of": payload["as_of"],
            "synced_at": payload["synced_at"],
            "sha256": corrupt_sha or hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    sp500_factsheet.clear_cache()


@pytest.fixture
def root(tmp_path, monkeypatch):
    directory = tmp_path / "snapshots"
    directory.mkdir()
    monkeypatch.setenv(sp500_factsheet.SNAPSHOT_DIR_ENV, str(directory))
    sp500_factsheet.clear_cache()
    yield directory
    sp500_factsheet.clear_cache()


# --------------------------------------------------------------------------
# modo offline: sin red, sin vendor, y el snapshot mas reciente <= la fecha
# --------------------------------------------------------------------------


def test_reads_the_newest_snapshot_not_after_the_requested_date(root):
    _install(root, [_payload("2026-06-30"), _payload("2026-08-31")])
    result = read_factsheet(date(2026, 7, 1))
    assert result["available"] is True
    assert result["snapshot_as_of"] == "2026-06-30"
    assert result["payload"]["metrics"]["weight_top_ten_pct"] == 37.8
    assert result["requested_date"] == "2026-07-01"


def test_a_future_snapshot_is_never_served_for_an_earlier_date(root):
    _install(root, [_payload("2026-08-31")])
    result = read_factsheet(date(2026, 8, 30))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_VINTAGE_AFTER
    assert result["snapshot_as_of"] == "2026-08-31"
    assert result["requested_date"] == "2026-08-30"
    assert "payload" not in result


def test_no_directory_configured_means_no_snapshot_not_an_empty_one(monkeypatch):
    monkeypatch.delenv(sp500_factsheet.SNAPSHOT_DIR_ENV, raising=False)
    sp500_factsheet.clear_cache()
    result = read_factsheet(date(2026, 9, 20))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_DIR_NOT_CONFIGURED
    assert sp500_factsheet.snapshot_dir() is None


def test_no_files_means_no_snapshot_in_disk(root):
    result = read_factsheet(date(2026, 9, 20))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_NO_SNAPSHOT
    assert result["integrity_problems"] == []


def test_a_missing_date_never_falls_back_to_the_latest_snapshot(root):
    _install(root, [_payload("2026-08-31")])
    result = read_factsheet(None)
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_INVALID_DATE


# --------------------------------------------------------------------------
# integridad: el manifest manda y un sha que no casa no se sirve
# --------------------------------------------------------------------------


def test_a_snapshot_not_declared_in_the_manifest_is_not_served(root):
    _install(root, [_payload("2026-08-31")], declare=False)
    result = read_factsheet(date(2026, 9, 20))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_INTEGRITY
    assert any("no declarado" in problem for problem in result["integrity_problems"])


def test_a_tampered_snapshot_is_not_served(root):
    _install(root, [_payload("2026-08-31")], corrupt_sha="0" * 64)
    result = read_factsheet(date(2026, 9, 20))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_INTEGRITY


def test_a_snapshot_missing_its_provenance_is_not_served(root):
    incomplete = _payload("2026-08-31")
    del incomplete["source_url"]
    _install(root, [incomplete])
    assert read_factsheet(date(2026, 9, 20))["reason"] == sp500_factsheet.REASON_INTEGRITY


def test_a_snapshot_with_a_naive_timestamp_is_not_served(root):
    _install(root, [_payload("2026-08-31", synced_at="2026-09-02T07:30:00")])
    assert read_factsheet(date(2026, 9, 20))["reason"] == sp500_factsheet.REASON_INTEGRITY


def test_a_broken_manifest_is_not_served(root):
    _install(root, [_payload("2026-08-31")])
    (root / "manifest.json").write_text("{no es json")
    sp500_factsheet.clear_cache()
    result = read_factsheet(date(2026, 9, 20))
    assert result["available"] is False
    assert result["reason"] == sp500_factsheet.REASON_INTEGRITY


# --------------------------------------------------------------------------
# cache en memoria: se invalida al reescribir, no al reiniciar
# --------------------------------------------------------------------------


def test_the_cache_sees_a_rebuilt_snapshot_without_a_restart(root):
    _install(root, [_payload("2026-08-31", metrics={"constituents": 503, "weight_top_ten_pct": 37.8})])
    first = read_factsheet(date(2026, 9, 20))
    assert first["payload"]["metrics"]["weight_top_ten_pct"] == 37.8
    _install(root, [_payload("2026-08-31", metrics={"constituents": 503, "weight_top_ten_pct": 41.2})])
    second = read_factsheet(date(2026, 9, 20))
    assert second["payload"]["metrics"]["weight_top_ten_pct"] == 41.2


# --------------------------------------------------------------------------
# builder: parseo estricto y fail closed
# --------------------------------------------------------------------------


def test_builder_extracts_the_published_index_characteristics():
    builder = _builder()
    metrics, as_of = builder.extract_index_characteristics(FACTSHEET_TEXT)
    assert as_of == date(2026, 8, 31)
    assert metrics["constituents"] == 503
    assert metrics["weight_top_ten_pct"] == 37.8
    assert metrics["weight_largest_pct"] == 8.1
    assert metrics["largest_total_market_cap_usd_m"] == 5347407.51


def test_the_as_of_date_does_not_swallow_the_index_values():
    """'AS OF AUGUST 31, 2026' va detras de los pesos: 31 no es un valor."""
    builder = _builder()
    metrics, _ = builder.extract_index_characteristics(FACTSHEET_TEXT)
    assert metrics["weight_top_ten_pct"] == 37.8
    assert metrics["constituents"] == 503


def test_builder_snapshot_carries_vintage_source_and_licence(tmp_path):
    builder = _builder()
    payload = builder.build_snapshot(
        FACTSHEET_TEXT,
        synced_at=datetime(2026, 9, 2, 7, 30, tzinfo=UTC),
        source_url="https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
        document_sha256="a" * 64,
        retrieved_from="https://example.org/factsheet.pdf",
    )
    assert payload["as_of"] == "2026-08-31"
    assert payload["synced_at"].startswith("2026-09-02T07:30:00")
    assert payload["source_tier"] == sp500_factsheet.SOURCE_TIER
    assert payload["source_scope"] == sp500_factsheet.SOURCE_SCOPE
    assert "FOR USE WITH INSTITUTIONS ONLY" in payload["source_license"]
    assert payload["retrieved_from"] == "https://example.org/factsheet.pdf"
    assert payload["parser"]["document_sha256"] == "a" * 64

    out = tmp_path / "out"
    path = builder.write_snapshot(out, payload)
    assert path.name == "s-p-500-2026-08-31.json"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["snapshots"][f"factsheets/{path.name}"]["as_of"] == "2026-08-31"
    assert manifest["snapshots"][f"factsheets/{path.name}"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    # Y lo que escribe el builder es exactamente lo que el conector sirve.
    import os

    previous = os.environ.get(sp500_factsheet.SNAPSHOT_DIR_ENV)
    os.environ[sp500_factsheet.SNAPSHOT_DIR_ENV] = str(out)
    sp500_factsheet.clear_cache()
    try:
        result = read_factsheet(date(2026, 9, 20))
    finally:
        if previous is None:
            os.environ.pop(sp500_factsheet.SNAPSHOT_DIR_ENV, None)
        else:
            os.environ[sp500_factsheet.SNAPSHOT_DIR_ENV] = previous
        sp500_factsheet.clear_cache()
    assert result["available"] is True
    assert result["payload"]["metrics"]["weight_top_ten_pct"] == 37.8


@pytest.mark.parametrize(
    "text, expected",
    [
        ("sin tabla de caracteristicas", "no se encuentra el ancla"),
        (
            FACTSHEET_TEXT.replace("136,835.41\n5,347,407.51\n5,858.44\n44,734.65", "136,835.41"),
            "se esperaban 7 valores",
        ),
        (FACTSHEET_TEXT.replace("8.1\n37.8", "8.1\n137.8"), "pesos incoherentes"),
        (FACTSHEET_TEXT.replace("5,858.44", "99,858.44"), "capitalizaciones incoherentes"),
        (FACTSHEET_TEXT.replace("503\n", "7\n"), "numero de constituyentes fuera de rango"),
        (FACTSHEET_TEXT.replace("AS OF AUGUST 31, 2026", "AS OF SMARCH 31, 2026"), "mes no reconocido"),
        (FACTSHEET_TEXT.replace("AS OF AUGUST 31, 2026", "AS OF FEBRUARY 30, 2026"), "fecha inexistente"),
        (FACTSHEET_TEXT.replace("AS OF AUGUST 31, 2026", "sin fecha"), "no declara 'AS OF <mes>"),
    ],
)
def test_builder_fails_closed_instead_of_guessing(text, expected):
    builder = _builder()
    with pytest.raises(builder.FactsheetError) as excinfo:
        builder.extract_index_characteristics(text)
    assert expected in str(excinfo.value)


def test_builder_refuses_a_snapshot_whose_date_does_not_match():
    builder = _builder()
    with pytest.raises(builder.FactsheetError):
        builder.build_snapshot(
            FACTSHEET_TEXT,
            synced_at=datetime(2026, 9, 2, 7, 30, tzinfo=UTC),
            source_url="https://example.org/fs.pdf",
            expected_as_of=date(2026, 7, 31),
        )


def test_builder_refuses_a_naive_or_impossible_sync_clock():
    builder = _builder()
    with pytest.raises(builder.FactsheetError):
        builder.build_snapshot(FACTSHEET_TEXT, synced_at=datetime(2026, 9, 2, 7, 30), source_url="x")
    with pytest.raises(builder.FactsheetError):
        builder.build_snapshot(
            FACTSHEET_TEXT,
            synced_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_url="x",
        )


def test_builder_reads_html_and_txt_sources(tmp_path):
    builder = _builder()
    html = tmp_path / "fs.html"
    html.write_text("<html><body><p>Index Characteristics</p>" + FACTSHEET_TEXT + "</body></html>")
    metrics, as_of = builder.extract_index_characteristics(builder.document_text(html))
    assert as_of == date(2026, 8, 31)
    assert metrics["weight_top_ten_pct"] == 37.8
    txt = tmp_path / "fs.txt"
    txt.write_text(FACTSHEET_TEXT)
    assert builder.extract_index_characteristics(builder.document_text(txt))[0]["constituents"] == 503


def test_repository_snapshots_are_parseable_and_versioned():
    """Los snapshots construidos son legibles y con vintage declarado.

    ``data/`` esta en ``.gitignore`` (los snapshots son datos, no fuente), asi
    que este test solo corre donde el script ya se ha ejecutado.
    """
    directory = Path(__file__).resolve().parents[1] / "data" / "sp500_factsheet_snapshots"
    if not directory.exists():
        pytest.skip("sin snapshots desplegados en este checkout")
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["source_tier"] == sp500_factsheet.SOURCE_TIER
    assert manifest["snapshots"]
    for relative, declared in manifest["snapshots"].items():
        payload = json.loads((directory / relative).read_text())
        assert payload["as_of"] == declared["as_of"] == date.fromisoformat(declared["as_of"]).isoformat()
        assert payload["synced_at"].endswith("+00:00")
        assert payload["source_url"].startswith("https://")
        assert 0 < payload["metrics"]["weight_top_ten_pct"] <= 100
        assert 0 < payload["metrics"]["weight_largest_pct"] <= payload["metrics"]["weight_top_ten_pct"]
        # Solo agregados: la lista de pesos por constituyente no se distribuye.
        assert payload["source_scope"] == sp500_factsheet.SOURCE_SCOPE
        assert "leaders" not in payload["metrics"]
