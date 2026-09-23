"""Tests unitarios de calculo puro de `app.valuation.dilution_model`.

Sin BD, sin red: dilucion simple por ampliacion de capital.
"""

from __future__ import annotations

import math

import pytest

from app.valuation.dilution_model import DilutionInput, run_dilution


def _inputs(**overrides) -> DilutionInput:
    base = dict(
        current_shares=100.0,
        new_capital_needed=50.0,
        issuance_price=5.0,
        current_value_per_share=8.0,
    )
    base.update(overrides)
    return DilutionInput(**base)


def test_caso_base_valores_conocidos():
    result = run_dilution(_inputs())
    assert result["new_shares"] == pytest.approx(10.0)
    assert result["pro_forma_shares"] == pytest.approx(110.0)
    assert result["dilution_pct"] == pytest.approx(10.0 / 110.0)
    # El valor total de la empresa se reparte entre mas acciones.
    assert result["diluted_value_per_share"] == pytest.approx(8.0 * 100.0 / 110.0)
    assert result["trace"]["method"] == "simple_equity_dilution"
    assert result["trace"]["inputs"]["issuance_price"] == 5.0


def test_current_shares_no_positivas_lanza():
    with pytest.raises(ValueError, match="current_shares must be positive"):
        run_dilution(_inputs(current_shares=0.0))
    with pytest.raises(ValueError, match="current_shares must be positive"):
        run_dilution(_inputs(current_shares=-1.0))


def test_issuance_price_no_positivo_lanza():
    with pytest.raises(ValueError, match="issuance_price must be positive"):
        run_dilution(_inputs(issuance_price=0.0))
    with pytest.raises(ValueError, match="issuance_price must be positive"):
        run_dilution(_inputs(issuance_price=-2.0))


def test_capital_necesario_cero_no_diluye():
    result = run_dilution(_inputs(new_capital_needed=0.0))
    assert result["new_shares"] == 0.0
    assert result["pro_forma_shares"] == pytest.approx(100.0)
    assert result["dilution_pct"] == 0.0
    assert result["diluted_value_per_share"] == pytest.approx(8.0)


def test_capital_necesario_negativo_se_recorta_a_cero():
    """Borde: una necesidad de capital negativa no puede 'quemar' acciones."""
    result = run_dilution(_inputs(new_capital_needed=-500.0))
    assert result["new_shares"] == 0.0
    assert result["dilution_pct"] == 0.0
    assert result["diluted_value_per_share"] == pytest.approx(8.0)


def test_emision_muy_barata_diluye_casi_totalmente():
    result = run_dilution(
        _inputs(new_capital_needed=1_000_000.0, issuance_price=0.01)
    )
    assert result["new_shares"] == pytest.approx(100_000_000.0)
    assert result["dilution_pct"] > 0.99
    assert result["diluted_value_per_share"] < 0.01
    assert math.isfinite(result["diluted_value_per_share"])


def test_emision_muy_cara_diluye_poco():
    result = run_dilution(_inputs(new_capital_needed=1.0, issuance_price=1e6))
    assert result["new_shares"] == pytest.approx(1e-6)
    assert result["dilution_pct"] < 1e-7
    assert result["diluted_value_per_share"] == pytest.approx(8.0, rel=1e-6)


def test_valor_por_accion_cero_o_negativo_se_conserva():
    cero = run_dilution(_inputs(current_value_per_share=0.0))
    assert cero["diluted_value_per_share"] == 0.0
    negativo = run_dilution(_inputs(current_value_per_share=-3.0))
    assert negativo["diluted_value_per_share"] == pytest.approx(-3.0 * 100.0 / 110.0)


def test_identidad_valor_total_se_conserva():
    """El valor total pre-emision repartido entre las acciones pro forma."""
    result = run_dilution(_inputs())
    total_pre = 8.0 * 100.0
    assert result["diluted_value_per_share"] * result["pro_forma_shares"] == pytest.approx(
        total_pre
    )
