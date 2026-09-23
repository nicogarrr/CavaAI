"""Tests unitarios de calculo puro de `app.valuation.scenario_model`.

Sin BD, sin red: ponderacion probabilistica de escenarios.
"""

from __future__ import annotations

import math

import pytest

from app.valuation.scenario_model import Scenario, probability_weighted_value


def test_valor_esperado_ponderado_con_probabilidades_normales():
    result = probability_weighted_value(
        [
            Scenario("bear", 0.2, 10.0),
            Scenario("base", 0.5, 20.0),
            Scenario("bull", 0.3, 30.0),
        ]
    )
    assert result["expected_value"] == pytest.approx(21.0)
    assert result["trace"]["method"] == "probability_weighted_scenario"
    assert result["trace"]["probability_sum"] == pytest.approx(1.0)


def test_probabilidades_se_normalizan_si_no_suman_uno():
    result = probability_weighted_value(
        [
            Scenario("bear", 1.0, 10.0),
            Scenario("base", 1.0, 20.0),
            Scenario("bull", 2.0, 30.0),
        ]
    )
    assert result["trace"]["probability_sum"] == pytest.approx(4.0)
    assert result["expected_value"] == pytest.approx(22.5)
    normalized = {row["name"]: row["probability"] for row in result["scenarios"]}
    assert normalized == pytest.approx({"bear": 0.25, "base": 0.25, "bull": 0.50})
    assert sum(normalized.values()) == pytest.approx(1.0)


def test_lista_vacia_lanza():
    with pytest.raises(ValueError, match="at least one scenario is required"):
        probability_weighted_value([])


def test_probabilidades_no_positivas_lanzan():
    with pytest.raises(ValueError, match="scenario probabilities must be positive"):
        probability_weighted_value([Scenario("a", 0.0, 10.0), Scenario("b", 0.0, 20.0)])
    with pytest.raises(ValueError, match="scenario probabilities must be positive"):
        probability_weighted_value([Scenario("a", -1.0, 10.0), Scenario("b", -2.0, 20.0)])


def test_probabilidad_negativa_parcial_sigue_sumando_positiva():
    # Caso borde: mezcla de signos con suma positiva se normaliza igualmente.
    result = probability_weighted_value(
        [Scenario("a", -0.5, 10.0), Scenario("b", 1.5, 20.0)]
    )
    assert result["trace"]["probability_sum"] == pytest.approx(1.0)
    assert result["expected_value"] == pytest.approx(
        -0.5 * 10.0 + 1.5 * 20.0
    )


def test_escenario_unico_queda_con_probabilidad_uno():
    result = probability_weighted_value([Scenario("solo", 0.37, 42.0)])
    assert result["scenarios"][0]["probability"] == pytest.approx(1.0)
    assert result["expected_value"] == pytest.approx(42.0)


def test_valores_negativos_y_cero_son_validos():
    result = probability_weighted_value(
        [
            Scenario("quiebra", 0.5, -10.0),
            Scenario("nulo", 0.25, 0.0),
            Scenario("recuperacion", 0.25, 5.0),
        ]
    )
    assert result["expected_value"] == pytest.approx(-3.75)
    assert math.isfinite(result["expected_value"])


def test_valores_extremos_no_desbordan_el_ponderado():
    result = probability_weighted_value(
        [Scenario("cisne", 0.01, 1e12), Scenario("base", 0.99, 1.0)]
    )
    assert result["expected_value"] == pytest.approx(0.01 * 1e12 + 0.99 * 1.0)
    assert math.isfinite(result["expected_value"])


def test_escenarios_devueltos_conservan_nombre_y_valor():
    result = probability_weighted_value([Scenario("a", 1.0, 3.0), Scenario("b", 3.0, 9.0)])
    assert [row["name"] for row in result["scenarios"]] == ["a", "b"]
    assert [row["value_per_share"] for row in result["scenarios"]] == [3.0, 9.0]
