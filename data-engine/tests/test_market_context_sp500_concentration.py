"""Concentracion top-10 del S&P 500: vintage explicito, sin look-ahead y sin ceros.

La metrica deja de estar permanentemente "no disponible" (el peso top-10 lo
publica el proveedor del indice, sin clave y gratis) sin comprar eso con
look-ahead: un snapshot con `as_of` solo responde para fechas >= `as_of`, y para
fechas anteriores devuelve "sin datos" con el motivo y las dos fechas, nunca un
numero. Estos tests fijan ese contrato.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base
from app.services.connectors import sp500_factsheet
from app.services.market_regime_quant import sp500_top_ten_concentration
from app.services.market_snapshot_service import build_snapshot, latest_snapshot

SOURCE_URL = "https://www.spglobal.com/spdji/en/indices/equity/sp-500/"


def _payload(as_of: str, **metrics) -> dict:
    base = {
        "constituents": 503,
        "weight_top_ten_pct": 37.8,
        "weight_largest_pct": 8.1,
        "mean_total_market_cap_usd_m": 136835.41,
    }
    return {
        "index": "S&P 500",
        "as_of": as_of,
        "synced_at": "2026-09-02T07:30:00+00:00",
        "source": "S&P 500 Index Factsheet (S&P Dow Jones Indices)",
        "source_url": SOURCE_URL,
        "source_tier": "index_provider_official",
        "source_license": "descarga publica sin clave; solo agregados",
        "source_scope": "aggregate_index_characteristics_only",
        "metrics": {**base, **metrics},
    }


def _write_snapshot(root, payload: dict, *, declared_as_of: str | None = None) -> None:
    """Escribe snapshot + manifest con sha256 declarado (como el builder)."""
    import hashlib

    (root / "factsheets").mkdir(parents=True, exist_ok=True)
    relative = f"factsheets/sp500-{payload['as_of']}.json"
    path = root / relative
    path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"snapshots": {}}
    manifest.setdefault("snapshots", {})[relative] = {
        "as_of": declared_as_of or payload["as_of"],
        "synced_at": payload["synced_at"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    sp500_factsheet.clear_cache()


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    root = tmp_path / "sp500_snapshots"
    root.mkdir()
    monkeypatch.setenv(sp500_factsheet.SNAPSHOT_DIR_ENV, str(root))
    sp500_factsheet.clear_cache()
    yield root
    sp500_factsheet.clear_cache()


# --------------------------------------------------------------------------
# (a) snapshot presente y fecha >= as_of -> concentracion con fuente
# --------------------------------------------------------------------------


def test_date_equal_or_after_as_of_returns_sourced_concentration(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))

    same_day = sp500_top_ten_concentration(date(2026, 8, 31))
    assert same_day["status"] == "disponible"
    assert same_day["fraction"] == pytest.approx(0.378)
    assert same_day["weight_top_ten_pct"] == 37.8
    assert same_day["weight_largest_pct"] == 8.1
    assert same_day["constituents"] == 503
    # La fuente viaja con el dato: sin cita el numero no es utilizable.
    assert same_day["source_url"] == SOURCE_URL
    assert same_day["source_tier"] == "index_provider_official"
    assert same_day["synced_at"] == "2026-09-02T07:30:00+00:00"
    assert same_day["date"] == "2026-08-31"
    assert same_day["requested_date"] == "2026-08-31"

    later = sp500_top_ten_concentration(date(2026, 9, 20))
    assert later["status"] == "disponible"
    # La fecha pedida no reescribe el vintage del dato.
    assert later["requested_date"] == "2026-09-20"
    assert later["date"] == "2026-08-31"
    assert later["age_days"] == 20


def test_each_date_gets_the_snapshot_current_at_that_date(snapshot_dir):
    """Con varios vintages, cada fecha recibe el suyo y no el mas reciente."""
    _write_snapshot(snapshot_dir, _payload("2026-06-30", weight_top_ten_pct=36.4, weight_largest_pct=7.5))
    _write_snapshot(snapshot_dir, _payload("2026-08-31", weight_top_ten_pct=37.8, weight_largest_pct=8.1))

    july = sp500_top_ten_concentration(date(2026, 7, 15))
    assert (july["date"], july["weight_top_ten_pct"]) == ("2026-06-30", 36.4)
    september = sp500_top_ten_concentration(date(2026, 9, 15))
    assert (september["date"], september["weight_top_ten_pct"]) == ("2026-08-31", 37.8)


# --------------------------------------------------------------------------
# (b) fecha < as_of -> no disponible con motivo, NUNCA un numero
# --------------------------------------------------------------------------


def test_date_before_as_of_is_unavailable_with_reason_and_no_number(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31", weight_top_ten_pct=37.8))

    past = sp500_top_ten_concentration(date(2026, 5, 15))

    assert past["status"] == "sin datos"
    assert past["available"] is False
    assert past["reason"] == "snapshot_vintage_after_requested_date"
    # Trazable: se sabe que hay snapshot, de que fecha, y de donde sale.
    assert past["requested_date"] == "2026-05-15"
    assert past["snapshot_as_of"] == "2026-08-31"
    assert past["snapshot_source_url"] == SOURCE_URL
    # Y no hay ningun numero camuflado de concentracion.
    assert "fraction" not in past
    assert "weight_top_ten_pct" not in past
    assert "leaders" not in past
    assert past.get("constituents") is None


def test_unavailable_never_carries_a_zero(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    past = sp500_top_ten_concentration(date(2026, 1, 1))
    assert past["status"] == "sin datos"
    for banned in ("fraction", "weight_top_ten_pct", "weight_largest_pct", "leaders"):
        assert banned not in past
    assert past.get("constituents") is None
    # Ningun valor numerico (los booleanos False no cuentan como cero).
    assert not [
        value for value in past.values()
        if isinstance(value, int | float) and not isinstance(value, bool) and value == 0
    ]


# --------------------------------------------------------------------------
# (c) snapshot ausente -> no disponible con motivo, nunca 0
# --------------------------------------------------------------------------


def test_without_snapshot_dir_configured_it_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv(sp500_factsheet.SNAPSHOT_DIR_ENV, raising=False)
    sp500_factsheet.clear_cache()
    result = sp500_top_ten_concentration(date(2026, 9, 20))
    assert result["status"] == "sin datos"
    assert result["available"] is False
    assert result["reason"] == "snapshot_dir_not_configured"
    assert "fraction" not in result


def test_empty_snapshot_dir_is_unavailable_not_zero(snapshot_dir):
    result = sp500_top_ten_concentration(date(2026, 9, 20))
    assert result["status"] == "sin datos"
    assert result["reason"] == "no_snapshot_in_disk"
    assert "fraction" not in result


def test_a_missing_date_is_unavailable_instead_of_guessing_the_vintage(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    result = sp500_top_ten_concentration(None)
    assert result["status"] == "sin datos"
    assert result["reason"] == "requested_date_invalid"


def test_a_stale_snapshot_is_not_presented_as_today(snapshot_dir):
    """Un factsheet mensual muy viejo no describe la concentracion de hoy."""
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    from app.services.market_regime_quant import SP500_FACTSHEET_MAX_AGE_DAYS

    requested = date(2026, 8, 31) + timedelta(days=SP500_FACTSHEET_MAX_AGE_DAYS + 1)
    result = sp500_top_ten_concentration(requested)
    assert result["status"] == "sin datos"
    assert result["available"] is False
    assert result["reason"] == "snapshot_too_stale_for_requested_date"
    assert result["age_days"] > SP500_FACTSHEET_MAX_AGE_DAYS
    assert "fraction" not in result


# --------------------------------------------------------------------------
# (d) la respuesta no inventa pesos si la fuente no los publica
# --------------------------------------------------------------------------


def test_composition_without_weights_reports_no_weights(snapshot_dir):
    """Una fuente que solo da composicion no habilita concentracion."""
    payload = _payload("2026-08-31")
    payload["metrics"] = {"constituents": 503, "composition_note": "sin pesos por constituyente"}
    _write_snapshot(snapshot_dir, payload)

    result = sp500_top_ten_concentration(date(2026, 9, 20))
    assert result["status"] == "sin datos"
    assert result["available"] is False
    assert result["reason"] == "index_weights_not_published_by_source"
    assert "fraction" not in result
    assert "weight_top_ten_pct" not in result
    # La procedencia del snapshot sigue declarada aunque no haya numero.
    assert result["snapshot_as_of"] == "2026-08-31"
    assert result["source_url"] == SOURCE_URL


@pytest.mark.parametrize("fake_weight", [0, -3.2, 101.0, 250, "37.8", None, True])
def test_a_nonsensical_published_weight_is_refused(snapshot_dir, fake_weight):
    _write_snapshot(snapshot_dir, _payload("2026-08-31", weight_top_ten_pct=fake_weight))
    result = sp500_top_ten_concentration(date(2026, 9, 20))
    assert result["status"] == "sin datos"
    assert result["available"] is False
    assert "fraction" not in result


def test_weights_are_taken_from_the_source_never_derived(snapshot_dir):
    """El peso publicado llega tal cual: no se reescala ni se 'completa'."""
    _write_snapshot(snapshot_dir, _payload("2026-08-31", weight_top_ten_pct=37.8, weight_largest_pct=8.1))
    result = sp500_top_ten_concentration(date(2026, 9, 20))
    assert result["fraction"] == pytest.approx(result["weight_top_ten_pct"] / 100)
    # No hay pesos por constituyente: el metodo no se los inventa.
    assert "leaders" not in result
    assert "no es un calculo propio" in result["method"]


# --------------------------------------------------------------------------
# (e) el shape de GET /market/regime no se rompe
# --------------------------------------------------------------------------


def test_regime_endpoint_shape_survives_the_new_metric(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        snapshot = build_snapshot(db, date(2026, 9, 20), datetime(2026, 9, 20, 22, 0, tzinfo=UTC))
        payload = latest_snapshot(db)

    # Claves que los consumidores ya leen: siguen existiendo.
    for key in ("status", "coverage", "metrics", "probabilities", "portfolio_beta", "model_version", "date"):
        assert key in payload
    for key in ("hmm", "top_ten_sp500", "portfolio_beta"):
        assert key in snapshot.metrics
    # Y top_ten_sp500 gana metricas sin perder las que tenia.
    top_ten = payload["metrics"]["top_ten_sp500"]
    assert top_ten["status"] == "disponible"
    assert top_ten["fraction"] == pytest.approx(0.378)
    assert top_ten["source_url"] == SOURCE_URL
    # hmm sigue igual: esta metrica no toca el modelo de regimen.
    assert payload["metrics"]["hmm"]["status"] == "sin datos"


def test_regime_shape_when_the_metric_cannot_be_answered(snapshot_dir):
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        build_snapshot(db, date(2026, 5, 15), datetime(2026, 5, 15, 22, 0, tzinfo=UTC))
        payload = latest_snapshot(db)
    top_ten = payload["metrics"]["top_ten_sp500"]
    assert top_ten["status"] == "sin datos"
    assert top_ten["reason"] == "snapshot_vintage_after_requested_date"
    assert "fraction" not in top_ten


# --------------------------------------------------------------------------
# (f) asercion explicita anti-look-ahead
# --------------------------------------------------------------------------


def test_no_requested_date_ever_receives_a_newer_snapshot(snapshot_dir):
    """Invariante: para toda fecha servida, as_of(snapshot) <= fecha pedida."""
    _write_snapshot(snapshot_dir, _payload("2026-06-30", weight_top_ten_pct=36.4))
    _write_snapshot(snapshot_dir, _payload("2026-08-31", weight_top_ten_pct=37.8))
    served = 0
    for ordinal in range(1, 200):
        requested = date(2026, 1, 1) + timedelta(days=ordinal)
        result = sp500_top_ten_concentration(requested)
        if result["status"] != "disponible":
            # Lo unico admisible sin numero es "sin datos" con motivo.
            assert result["reason"]
            assert "fraction" not in result
            continue
        served += 1
        assert date.fromisoformat(result["snapshot_as_of"]) <= requested
        assert date.fromisoformat(result["date"]) == date.fromisoformat(result["snapshot_as_of"])
    assert served > 0


def test_adding_a_snapshot_today_does_not_rewrite_the_past(snapshot_dir):
    """Backfill: ingestar hoy el factsheet de agosto no habilita julio."""
    _write_snapshot(snapshot_dir, _payload("2026-08-31"))
    before = sp500_top_ten_concentration(date(2026, 7, 1))
    _write_snapshot(snapshot_dir, _payload("2026-09-30", weight_top_ten_pct=38.1))
    after = sp500_top_ten_concentration(date(2026, 7, 1))
    assert before["status"] == after["status"] == "sin datos"
    assert after["reason"] == "snapshot_vintage_after_requested_date"
    # Sigue sabiendo cual es el snapshot que no puede usar, y de donde vino.
    assert after["snapshot_as_of"] == "2026-09-30"
    assert after["snapshot_source_tier"] == "index_provider_official"
