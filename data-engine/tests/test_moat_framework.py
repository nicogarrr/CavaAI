"""Tests unitarios de `app.valuation.moat_framework` (andamiaje cualitativo).

Sin BD, sin red: el marco de foso (moat) nunca fabrica afirmaciones
cualitativas — solo estructura trazable pendiente de evidencia con fuente.
"""

from __future__ import annotations

from app.valuation.moat_framework import (
    MOAT_CATEGORIES,
    MoatEvidence,
    empty_moat_framework,
)


def test_tags_software_plataforma_sugieren_switching_costs_y_data():
    result = empty_moat_framework("operating_software", ["software", "platform"], [])
    types = [m["type"] for m in result["moats"]]
    assert types == ["switching_costs", "data_advantage"]
    assert result["status"] == "scaffold_only"
    assert result["company_type"] == "operating_software"


def test_ningun_moat_lleva_fuerza_afirmada():
    result = empty_moat_framework("x", ["software", "space", "quality", "commodities"], [])
    for moat in result["moats"]:
        assert moat["strength"] == 0.0
        assert moat["confidence"] == 0.0
        assert moat["trend"] == "unknown"
        assert moat["status"] == "requires_sourced_evidence"
        assert moat["persistence_years"] is None


def test_tags_telecom_espacio_incluyen_barreras_regulatorias_y_capital():
    result = empty_moat_framework("satellite_operator", ["telecom", "space"], ["riesgo_regulatorio"])
    types = [m["type"] for m in result["moats"]]
    assert types == ["regulatory_barriers", "capital_intensity_barrier"]
    reg = result["moats"][0]
    assert any("requires primary source" in text for text in reg["evidence_for"])
    assert any("requires sourced comparison" in text for text in reg["evidence_against"])
    assert result["special_risks"] == ["riesgo_regulatorio"]


def test_tag_quality_sugiere_intangibles():
    result = empty_moat_framework("brand", ["quality"], [])
    assert [m["type"] for m in result["moats"]] == ["intangible_assets"]


def test_tag_commodities_marca_aceptacion_de_precios():
    result = empty_moat_framework("miner", ["commodities"], [])
    moat = result["moats"][0]
    assert moat["type"] == "cost_advantage"
    assert any("price taker" in text for text in moat["evidence_against"])


def test_sin_tags_cae_en_esqueleto_por_defecto():
    result = empty_moat_framework("unknown", [], [])
    types = [m["type"] for m in result["moats"]]
    assert types == list(MOAT_CATEGORIES[:3])


def test_tags_desconocidos_sin_duplicados():
    result = empty_moat_framework("mixto", ["space", "telecom", "software", "software"], [])
    types = [m["type"] for m in result["moats"]]
    assert len(types) == len(set(types))
    assert set(types) == {
        "switching_costs",
        "data_advantage",
        "regulatory_barriers",
        "capital_intensity_barrier",
    }


def test_case_insensitive_no_rompe_y_no_sugiere_nada_inventado():
    """Un tag con distinta capitalizacion no matchea y cae al esqueleto neutro."""
    result = empty_moat_framework("x", ["Software"], [])
    assert [m["type"] for m in result["moats"]] == list(MOAT_CATEGORIES[:3])


def test_advertencia_explicita_de_analisis_incompleto():
    result = empty_moat_framework("x", ["software"], [])
    assert "requires" in result["note"] or "sourced evidence" in result["note"]
    assert "Do not treat this scaffold as a completed competitive analysis" in result["note"]


def test_moat_evidence_serializa_campos_documentados():
    evidence = MoatEvidence(type="switching_costs", strength=0.5, trend="strengthening")
    assert evidence.evidence_for == []
    assert evidence.evidence_against == []
    assert evidence.persistence_years is None
    assert evidence.status == "requires_sourced_evidence"
