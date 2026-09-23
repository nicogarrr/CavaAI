"""Tests unitarios de calculo puro de `app.valuation.commodity_sensitivity`.

Sin BD, sin red: sensibilidad del valor a precios de materia prima.
"""

from __future__ import annotations

import math

import pytest

from app.valuation.commodity_sensitivity import commodity_price_sensitivity


def _run(prices=None, **overrides):
    kwargs = dict(
        base_volume=1000.0,
        cash_cost_per_unit=5.0,
        commodity_prices=[0.0, 5.0, 10.0, 20.0] if prices is None else prices,
        tax_rate=0.25,
        multiple=8.0,
        net_debt=100.0,
        shares_outstanding=500.0,
    )
    kwargs.update(overrides)
    return commodity_price_sensitivity(**kwargs)


def test_caso_base_valores_conocidos():
    result = _run()
    rows = result["rows"]
    assert result["trace"]["method"] == "commodity_price_sensitivity"
    assert [row["commodity_price"] for row in rows] == [0.0, 5.0, 10.0, 20.0]

    # price 10: ebitda = (10-5)*1000 = 5000; after_tax 3750; equity 30000-100.
    assert rows[2]["after_tax_cash_flow"] == pytest.approx(3750.0)
    assert rows[2]["equity_value"] == pytest.approx(29_900.0)
    assert rows[2]["value_per_share"] == pytest.approx(59.8)

    # price 20: ebitda 15000; after_tax 11250; equity 90000-100 = 89900.
    assert rows[3]["equity_value"] == pytest.approx(89_900.0)
    assert rows[3]["value_per_share"] == pytest.approx(179.8)


def test_precio_por_debajo_del_coste_no_genera_perdida_operativa():
    """El EBITDA se recorta a cero: nunca se modelan perdidas operativas."""
    result = _run(prices=[0.0, 2.5, 5.0])
    for row in result["rows"]:
        assert row["after_tax_cash_flow"] == 0.0
        # Solo queda la deuda: valor negativo de equity, sin apalancar el EBITDA.
        assert row["equity_value"] == pytest.approx(-100.0)
        assert row["value_per_share"] == pytest.approx(-0.2)


def test_shares_no_positivas_lanza():
    with pytest.raises(ValueError, match="shares_outstanding must be positive"):
        _run(shares_outstanding=0.0)
    with pytest.raises(ValueError, match="shares_outstanding must be positive"):
        _run(shares_outstanding=-10.0)


def test_lista_de_precios_vacia_devuelve_filas_vacias():
    result = _run(prices=[])
    assert result["rows"] == []
    assert result["trace"]["method"] == "commodity_price_sensitivity"


def test_precio_unitario_exacto_equilibra_coste():
    """price == cash_cost -> EBITDA 0 (borde de la funcion max)."""
    result = _run(prices=[5.0])
    assert result["rows"][0]["after_tax_cash_flow"] == 0.0
    assert result["rows"][0]["equity_value"] == pytest.approx(-100.0)


def test_tasa_impositiva_del_cien_por_cien_anula_el_flujo():
    result = _run(prices=[50.0], tax_rate=1.0)
    assert result["rows"][0]["after_tax_cash_flow"] == 0.0
    assert result["rows"][0]["equity_value"] == pytest.approx(-100.0)


def test_tasa_impositiva_cero_seria_el_flujo_bruto():
    result = _run(prices=[10.0], tax_rate=0.0)
    assert result["rows"][0]["after_tax_cash_flow"] == pytest.approx(5000.0)


def test_precio_extremo_sigue_finito():
    result = _run(prices=[1e9])
    row = result["rows"][0]
    assert math.isfinite(row["value_per_share"])
    esperado = ((1e9 - 5.0) * 1000.0 * 0.75 * 8.0 - 100.0) / 500.0
    assert row["value_per_share"] == pytest.approx(esperado)


def test_volumen_cero_da_solo_deuda():
    result = _run(prices=[100.0], base_volume=0.0)
    assert result["rows"][0]["after_tax_cash_flow"] == 0.0
    assert result["rows"][0]["equity_value"] == pytest.approx(-100.0)


def test_monotonia_en_precio():
    """A mayor precio de commodity, mayor valor por accion."""
    result = _run(prices=[10.0, 20.0, 30.0, 40.0])
    values = [row["value_per_share"] for row in result["rows"]]
    assert values == sorted(values)
    assert len(set(values)) == len(values)
