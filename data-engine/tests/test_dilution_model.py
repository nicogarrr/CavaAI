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
    # El equity post-emision es el pre-emision mas el capital captado, y ese
    # equity se reparte entre las acciones pro forma: (800 + 50) / 110.
    # Repartir solo el equity pre-emision (8,00 * 100 / 110 = 7,27) trataba el
    # capital captado como si no tuviera valor, es decir como una emision
    # siempre con descuento, y destruia valor en cualquier caso.
    assert result["diluted_value_per_share"] == pytest.approx((800.0 + 50.0) / 110.0)
    assert result["trace"]["method"] == "pro_forma_equity_with_issuance_credit"
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
    # Emitir 1.000.000 a 0,01 contra un valor previo de 8,00 es una emision
    # tematicamente barata: destruye el 99,99% del valor por accion. El
    # capital captado sigue valiendo algo, asi que el resultado es
    # (800 + 1.000.000) / 100.000.100 y no exactamente cero.
    assert result["diluted_value_per_share"] == pytest.approx(
        (800.0 + 1_000_000.0) / 100_000_100.0
    )
    assert result["diluted_value_per_share"] < 8.0
    assert math.isfinite(result["diluted_value_per_share"])


def test_emision_muy_cara_es_acretiva():
    result = run_dilution(_inputs(new_capital_needed=1.0, issuance_price=1e6))
    assert result["new_shares"] == pytest.approx(1e-6)
    assert result["dilution_pct"] < 1e-7
    # 1 euro captado a 1.000.000 laaccion, con acciones valoradas en 8,00, es
    # ALTAMENTE acretiva: el emisor vende su equity muy por encima de su
    # valor contable, asi que el valor por accion sube a 801/100,000001.
    # Tratarel capital captado como si no tuviera valor lo dejaba en 8,00 y
    # ocultaba tanto la creacion como la destruccion de valor.
    assert result["diluted_value_per_share"] == pytest.approx(801.0 / 100.000001, rel=1e-9)
    assert result["diluted_value_per_share"] > 8.0
    assert result["issuance_premium_to_value"] == pytest.approx(125_000.0)


def test_valor_por_accion_cero_o_negativo_se_conserva():
    # Con equity previo cero, la caja captada sigue siendo valor: 50 captados
    # sobre 110 acciones son 0,4545 por accion, no 0. Decir 0 trataria el
    # dinero recibido como si no existiera.
    cero = run_dilution(_inputs(current_value_per_share=0.0))
    assert cero["diluted_value_per_share"] == pytest.approx(50.0 / 110.0)
    # Con equity negativo la empresa vale menos que cero, y emitir a 5 sobre
    # un valor de -3,00 es dilutivo respecto a la posicion previa.
    negativo = run_dilution(_inputs(current_value_per_share=-3.0))
    assert negativo["diluted_value_per_share"] == pytest.approx((-300.0 + 50.0) / 110.0)


def test_identidad_equity_post_emision_se_conserva():
    """El equity post-emision es el pre-emision mas el capital captado."""
    result = run_dilution(_inputs())
    assert result["pre_equity_value"] == pytest.approx(8.0 * 100.0)
    assert result["post_equity_value"] == pytest.approx(8.0 * 100.0 + 50.0)
    assert result["diluted_value_per_share"] * result["pro_forma_shares"] == pytest.approx(
        8.0 * 100.0 + 50.0
    )
