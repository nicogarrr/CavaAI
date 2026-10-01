"""Tests unitarios de `app.valuation.moat_framework` (regla de puntuacion).

Sin BD, sin red: el marco de foso (moat) nunca fabrica afirmaciones
cualitativas. Lo que antes era un andamiaje con scores a cero ahora son
categorias declaradas NO EVALUABLES, con `strength=None` y su estado, de modo
que un 0 nunca se presenta como si fuera una medida de ventaja competitiva.
"""

from __future__ import annotations

from app.valuation.moat_framework import (
    MOAT_CATEGORIES,
    NO_SOURCED_EVIDENCE,
    NOT_EVALUABLE_NOTE,
    SCORE_VERSION,
    STATUS_NOT_EVALUABLE,
    CategoryScore,
    EvidenceRef,
    MoatEvidence,
    aggregate_strength,
    empty_moat_framework,
    is_sourced_tier,
    overall_status,
    score_category,
    suggested_categories,
)


def _ref(**overrides) -> EvidenceRef:
    base = {
        "claim_id": 1,
        "evidence_id": 1,
        "relation": "supports",
        "source_tier": "tier_1_regulatory",
        "trust_score": 1.0,
        "confidence": 0.9,
    }
    return EvidenceRef(**(base | overrides))


def test_marco_sin_evaluar_no_declara_ninguna_puntuacion():
    result = empty_moat_framework("x", ["software", "space", "quality", "commodities"], [])
    assert result["status"] == STATUS_NOT_EVALUABLE
    assert result["moats"] == []
    assert result["aggregate_strength"] is None
    assert result["aggregate"]["comparable"] is False
    assert result["score_version"] == SCORE_VERSION
    assert result["note"] == NOT_EVALUABLE_NOTE
    for item in result["unevaluated_moats"]:
        assert item["strength"] is None
        assert item["evaluable"] is False
        assert item["status"] == NO_SOURCED_EVIDENCE
        assert item["confidence"] == 0.0
        assert item["trend"] == "uncertain"
        assert item["persistence"] == "unproven"
        assert item["evidence_for"] == []


def test_la_jerarquia_de_marcos_conserva_los_tipos_que_marca_el_riesgo():
    """`MoatEvidence` ya no afirma fuerza: su estado por defecto es no evaluable."""
    evidence = MoatEvidence(type="switching_costs")
    assert evidence.strength is None
    assert evidence.status == NO_SOURCED_EVIDENCE
    assert evidence.evaluable is False
    assert evidence.evidence_for == []
    assert evidence.evidence_against == []
    assert evidence.persistence_years is None
    assert evidence.as_dict()["evidence_to_review"] == []


def test_la_lista_de_revision_no_se_presenta_como_evidencia():
    result = empty_moat_framework("satellite_operator", ["telecom", "space"], ["riesgo_regulatorio"])
    assert [item["type"] for item in result["unevaluated_moats"]] == [
        "regulatory_barriers",
        "capital_intensity_barrier",
    ]
    checklist = result["review_checklist"]["regulatory_barriers"]
    assert any("Licencias" in text for text in checklist)
    for item in result["unevaluated_moats"]:
        # Lo que hay que buscar no es evidencia: vive en su propio campo.
        assert item["evidence_for"] == []
        assert item["evidence_to_review"] == result["review_checklist"][item["type"]]
    assert result["special_risks"] == ["riesgo_regulatorio"]


def test_sin_tags_cae_en_el_esqueleto_neutro():
    assert suggested_categories([]) == list(MOAT_CATEGORIES[:3])
    assert suggested_categories(["pelota", "software_x"]) == list(MOAT_CATEGORIES[:3])
    assert suggested_categories(["space", "telecom", "software", "software"]) == [
        "switching_costs",
        "data_advantage",
        "regulatory_barriers",
        "capital_intensity_barrier",
    ]
    assert suggested_categories(["quality"]) == ["intangible_assets"]
    assert suggested_categories(["commodities"]) == ["cost_advantage"]


def test_las_etiquetas_se_normalizan_antes_de_sugerir_categorias():
    """Las etiquetas llegan de la ficha del usuario: `Software` y `software` son
    la misma etiqueta y no deben dar dos listas de trabajo distintas."""
    assert suggested_categories(["Software", "SPACE"]) == [
        "switching_costs",
        "data_advantage",
        "regulatory_barriers",
        "capital_intensity_barrier",
    ]


def test_solo_los_tiers_con_fuente_primaria_pueden_sostener_un_score():
    assert is_sourced_tier("tier_1_regulatory", 1.0) is True
    assert is_sourced_tier("tier_3_transcript", 0.82) is True
    assert is_sourced_tier("tier_4_reputable_media", 0.72) is False
    assert is_sourced_tier("tier_7_user_input", 0.38) is False
    assert is_sourced_tier("tier_unknown", 0.25) is False
    assert is_sourced_tier(None, 1.0) is False
    # Nombre conocido pero confianza por debajo del minimo: tampoco puntua.
    assert is_sourced_tier("tier_3_transcript", 0.5) is False


def test_categoria_sin_evidencia_no_puntua_y_no_es_un_cero():
    score = score_category("brand", [])
    assert score.status == NO_SOURCED_EVIDENCE
    assert score.strength is None
    assert score.evaluable is False
    assert score.confidence == 0.0
    assert score.trend == "uncertain"
    assert score.persistence == "unproven"
    assert score.trace["method"] == SCORE_VERSION


def test_categoria_con_evidencia_de_fuente_primaria_puntua_y_es_trazable():
    score = score_category(
        "brand",
        [_ref(claim_id=7), _ref(claim_id=7, evidence_id=2)],
        keywords=("brand",),
    )
    assert score.status == "evidence_backed"
    assert score.strength == 40
    assert score.evaluable is True
    assert score.supporting_claim_ids == [7]
    assert [item["evidence_id"] for item in score.as_dict()["evidence_for"]] == [1, 2]
    assert all(item["source_tier"] == "tier_1_regulatory" for item in score.as_dict()["evidence_for"])


def test_la_evidencia_en_contra_cancela_la_puntuacion():
    score = score_category(
        "switching_costs",
        [
            _ref(source_tier="tier_2_company", trust_score=0.9, confidence=0.8),
            _ref(
                source_tier="tier_2_company",
                trust_score=0.9,
                confidence=0.8,
                relation="contradicts",
            ),
        ],
    )
    # Un 0 con evidencia en contra es un hallazgo, no una falta de dato.
    assert score.status == "limited_evidence"
    assert score.evaluable is True
    assert score.strength == 0
    assert score.contradicting_claim_ids == [1]


def test_agregado_sin_categorias_evaluables_no_es_un_numero():
    unevaluated = [
        CategoryScore(
            type="brand",
            status=NO_SOURCED_EVIDENCE,
            strength=None,
            trend="uncertain",
            persistence="unproven",
            confidence=0.0,
        )
    ]
    assert aggregate_strength([]) is None
    assert aggregate_strength(unevaluated) is None
    assert overall_status([], unevaluated) == STATUS_NOT_EVALUABLE


def test_agregado_pondera_por_confianza_y_excluye_lo_no_evaluable():
    strong = CategoryScore(
        type="brand",
        status="evidence_backed",
        strength=80,
        trend="stable",
        persistence="high",
        confidence=0.9,
    )
    weak = CategoryScore(
        type="scale",
        status="limited_evidence",
        strength=20,
        trend="uncertain",
        persistence="unproven",
        confidence=0.1,
    )
    assert aggregate_strength([strong, weak]) == 74  # (80*0.9 + 20*0.1) / 1.0
    assert overall_status([weak], []) == "partial_evidence"
    assert overall_status([weak, strong], []) == "evidence_backed"