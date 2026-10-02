"""Trazabilidad y honestidad del foso competitivo (MOAT_EVIDENCE_V2).

Este archivo fija las reglas que impiden que un foso inexistente se lea como un
foso de cero:

* una categoria con evidencia de fuente primaria se puntua y se puede
  audiciar claim por claim;
* una categoria sin evidencia NO se puntua: se declara y queda fuera del
  agregado;
* evidencia solo de tier bajo se reporta pero no se convierte en score;
* el shape que leen `valuation_service`, `red_team_service`, la vista de foso
  del frontend y `_moat_markdown` de la tesis no cambia ni se rompe.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Claim,
    ClaimEvidence,
    Company,
    MoatAssessment,
)
from app.services.moat_service import MOAT_KEYWORDS, MoatService
from app.valuation import moat_framework
from app.valuation.moat_framework import (
    NO_SOURCED_EVIDENCE,
    ONLY_LOW_TIER_EVIDENCE,
    STATUS_NOT_EVALUABLE,
    empty_moat_framework,
)

#: Claves que el frontend y el backend leen del assessment. Un contrato roto
#: aqui es un panel en blanco en produccion.
FRONTEND_TOP_LEVEL_KEYS = {"ticker", "status", "methodology", "moats"}
FRONTEND_MOAT_KEYS = {
    "type",
    "strength",
    "trend",
    "persistence",
    "confidence",
    "status",
    "supporting_claim_ids",
    "contradicting_claim_ids",
}

#: Columnas de la vista de foso (`app/research/[ticker]/page.tsx`).
RENDERED_IN_MOAT_VIEW = ["strength", "status", "trend", "persistence",
                         "supporting_claim_ids", "contradicting_claim_ids"]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Satellite", company_type="space_telecom_pre_fcf",
        valuation_model="probability_weighted_scenarios+dilution",
        special_sources=[], special_risks=["regulatorio"],
        factor_tags=["space", "telecom", "pre_fcf"],
    )
    db.add(company)
    db.commit()
    return company


def _claim(db: Session, company_id: int, statement: str, metadata: dict | None = None) -> Claim:
    claim = Claim(company_id=company_id, statement=statement, metadata_=metadata or {})
    db.add(claim)
    db.flush()
    return claim


def _evidence(
    db: Session,
    claim_id: int,
    *,
    tier: str,
    kind: str = "supports",
    confidence: float = 0.9,
):
    db.add(ClaimEvidence(
        claim_id=claim_id, source_tier=tier, evidence_type=kind,
        confidence=confidence, summary="ev",
    ))
    db.flush()


# (a) Evidencia suficiente -> score trazable claim por claim


def test_categoria_con_evidencia_suficiente_puntua_con_ids_trazables(db):
    company = _company(db)
    claim = _claim(db, company.id, "Licencias de espectro vigentes ante el regulador")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_2_company", confidence=0.9)

    result = MoatService().assess(db, company, persist=False)
    regulation = next(m for m in result["moats"] if m["type"] == "regulation")

    assert regulation["status"] == "evidence_backed"
    assert regulation["strength"] == 60
    assert regulation["evaluable"] is True
    # Trazabilidad: el score apunta a la claim y a cada evidencia con su tier.
    assert regulation["supporting_claim_ids"] == [claim.id]
    refs = regulation["evidence_for"]
    assert [ref["claim_id"] for ref in refs] == [claim.id] * 3
    assert [ref["source_tier"] for ref in refs] == [
        "tier_1_regulatory",
        "tier_1_regulatory",
        "tier_2_company",
    ]
    assert [ref["evidence_id"] for ref in refs] == sorted(
        ref["evidence_id"] for ref in refs
    )
    assert all(ref["counts_for_score"] is True for ref in refs)
    # Y la traza explica como se llego al numero.
    assert regulation["trace"]["method"] == "MOAT_EVIDENCE_V2"
    assert regulation["trace"]["scored_evidence_refs"] == 3
    assert regulation["trace"]["tier_policy"]["scoring_tiers"] == [
        "tier_1_regulatory",
        "tier_2_company",
        "tier_3_transcript",
    ]
    assert result["aggregate_strength"] == 60


# (b) Sin evidencia -> estado explicito, nunca un 0


def test_categoria_sin_evidencia_declara_estado_y_no_devuelve_cero(db):
    company = _company(db)
    result = MoatService().assess(db, company, persist=False)

    assert result["moats"] == []
    assert result["status"] == STATUS_NOT_EVALUABLE
    for item in result["unevaluated_moats"]:
        assert item["strength"] is None
        assert item["status"] == NO_SOURCED_EVIDENCE
        assert item["status_label"]
        # Lo que falta para poder puntuarla, sin presentarlo como encontrado.
        assert isinstance(item["evidence_to_review"], list)
        assert item["evidence_for"] == [] and item["evidence_against"] == []


def test_una_claim_sin_evidencia_no_cambia_el_estado_de_su_categoria(db):
    company = _company(db)
    _claim(db, company.id, "El lock-in de ecosistema se mantiene")
    result = MoatService().assess(db, company, persist=False)
    ecosystem = next(
        item for item in result["unevaluated_moats"] if item["type"] == "ecosystem"
    )
    assert ecosystem["status"] == NO_SOURCED_EVIDENCE
    assert ecosystem["strength"] is None
    assert ecosystem["trace"]["evidence_refs"] == 0


# (c) Solo tier bajo -> tratamiento definido


@pytest.mark.parametrize("tier", ["tier_4_reputable_media", "tier_5_data_provider",
                                  "tier_6_bootstrap", "tier_7_user_input",
                                  "tier_unknown"])
def test_evidencia_solo_de_tier_bajo_se_reporta_pero_no_puntua(db, tier):
    company = _company(db)
    claim = _claim(db, company.id, "Pricing power de marca sostiene el margen")
    for _ in range(4):
        _evidence(db, claim.id, tier=tier, confidence=0.9)

    result = MoatService().assess(db, company, persist=False)
    brand = next(
        item for item in result["unevaluated_moats"] if item["type"] == "brand"
    )
    assert brand["status"] == ONLY_LOW_TIER_EVIDENCE
    assert brand["evaluable"] is False
    assert brand["strength"] is None
    # Se conserva la referencia para que un humano pueda decidir si le vale:
    # se ve la evidencia que hubo y por que no se converting en score.
    assert brand["trace"]["low_tier_evidence_refs"] == 4
    assert brand["trace"]["scored_evidence_refs"] == 0
    assert len(brand["trace"]["uncounted_evidence"]) == 4
    assert all(ref["counts_for_score"] is False for ref in brand["trace"]["uncounted_evidence"])
    assert result["aggregate_strength"] is None
    assert result["status"] == STATUS_NOT_EVALUABLE


def test_una_sola_fuente_primaria_ya_es_una_puntuacion(db):
    """El corte es por tier de fuente, no por numero de referencias."""
    company = _company(db)
    claim = _claim(db, company.id, "Licencia de espectro en vigor")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)

    result = MoatService().assess(db, company, persist=False)
    regulation = next(m for m in result["moats"] if m["type"] == "regulation")
    assert regulation["status"] == "limited_evidence"
    assert regulation["evaluable"] is True
    assert regulation["strength"] == 20  # breadth 1/5 sobre el saldo completo
    assert result["status"] == "partial_evidence"


# (d) El agregado excluye lo no evaluable


def test_el_agregado_excluye_las_categorias_no_evaluables(db):
    company = _company(db)
    license_claim = _claim(db, company.id, "Espectro licenciado y en operacion")
    for _ in range(5):
        _evidence(db, license_claim.id, tier="tier_1_regulatory", confidence=0.9)
    # Evidencia de marca, pero solo de prensa: no puede entrar en el agregado.
    brand_claim = _claim(db, company.id, "Pricing power de marca en la practica")
    for _ in range(5):
        _evidence(db, brand_claim.id, tier="tier_4_reputable_media", confidence=0.9)
    # Una categoria sin nada de evidencia.
    _claim(db, company.id, "Retencion y lock-in de clientes finales")

    result = MoatService().assess(db, company, persist=False)
    assert [item["type"] for item in result["moats"]] == ["regulation"]
    excluded = {item["type"]: item["status"] for item in result["aggregate"]["excluded_categories"]}
    assert excluded["brand"] == ONLY_LOW_TIER_EVIDENCE
    assert excluded["switching_costs"] == NO_SOURCED_EVIDENCE
    assert excluded["ecosystem"] == NO_SOURCED_EVIDENCE
    # Un agregado de una sola categoria no puede prometer mas de lo que hay.
    assert result["aggregate_strength"] == result["moats"][0]["strength"]
    assert result["categories_evaluated"] == 1
    assert result["categories_total"] == len(MOAT_KEYWORDS)


def test_sin_nada_evaluable_no_hay_agregado_numerico(db):
    company = _company(db)
    result = MoatService().assess(db, company, persist=False)
    assert result["aggregate_strength"] is None
    assert result["aggregate"]["strength"] is None
    assert result["aggregate"]["comparable"] is False
    assert result["aggregate"]["evaluated_categories"] == []
    assert "0" not in json.dumps(result["aggregate_strength"])


# (e) El shape que consume el frontend no se rompe


def test_el_shape_que_lectura_el_frontend_no_se_rompe(db):
    company = _company(db)
    claim = _claim(db, company.id, "Switching cost alto por integracion profunda")
    _evidence(db, claim.id, tier="tier_2_company", confidence=0.9)
    _evidence(db, claim.id, tier="tier_2_company", confidence=0.9)

    for result in (
        MoatService().assess(db, company, persist=True),
        MoatService().read(db, company),
    ):
        assert set(result) >= FRONTEND_TOP_LEVEL_KEYS
        assert isinstance(result["moats"], list)
        for moat in result["moats"]:
            assert set(moat) >= FRONTEND_MOAT_KEYS
            for key in RENDERED_IN_MOAT_VIEW:
                assert key in moat
            # `page.tsx` pinta `{item.strength}/100` y el indice de claves del
            # glosario necesita `item.type`: ambos deben ser utilizables tal cual.
            assert isinstance(moat["strength"], int)
            assert isinstance(moat["supporting_claim_ids"], list)
            assert isinstance(moat["contradicting_claim_ids"], list)
            assert moat["type"] in moat_framework.MOAT_CATEGORIES or moat["type"] in MOAT_KEYWORDS


def test_el_markdown_de_la_tesis_puede_formatear_el_foco_sin_romperse(db):
    """`_moat_markdown` formatea la fuerza con `:.2f`: un None lo rompe."""
    company = _company(db)
    result = MoatService().assess(db, company, persist=False)
    framework = empty_moat_framework(
        company.company_type, company.factor_tags or [], company.special_risks or []
    )
    for payload in (result, framework):
        for item in payload["moats"]:
            assert f"{item['strength']:.2f}"
        # El marcador de nota que usa `thesis_service` sigue presente.
        assert payload.get("note")


# (f) El vocabulary del andamiaje desaparece


def test_no_queda_rastro_de_andamiaje_en_la_respuesta(db):
    company = _company(db)
    claim = _claim(db, company.id, "Brand pricing power con evidencia primaria")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)

    payloads = [
        MoatService().assess(db, company, persist=True),
        MoatService().read(db, company),
        empty_moat_framework("standard", ["software"], []),
    ]
    for payload in payloads:
        blob = json.dumps(payload, default=str).lower()
        assert "scaffold" not in blob
        assert "scaffold_only" not in payload.get("status", "")
        assert payload["status"] in {
            "evidence_backed",
            "partial_evidence",
            STATUS_NOT_EVALUABLE,
        }


def test_el_modulo_ya_no_declara_un_andamiaje():
    with open(moat_framework.__file__, encoding="utf-8") as handle:
        source = handle.read().lower()
    assert "scaffold" not in source
    assert "requires_sourced_evidence" not in source


def test_perfil_operativo_no_es_un_veredicto_de_foso(db):
    """El perfil sigue siendo contexto: no puntua ni recorta evidencia."""
    company = _company(db)
    result = MoatService().assess(db, company, persist=False)
    context = result["profile_context"]
    assert context["profile"] == "early_stage"
    assert context["score_comparable"] is False
    assert context["note"]
    # Un perfil no comparable no puede dejar al assessment sin evaluable.
    assert len(result["unevaluated_moats"]) == len(MOAT_KEYWORDS)


def test_una_fila_persistida_por_la_politica_antigua_no_entra_en_el_agregado(db):
    """Las filas heredadas se muestran, pero su regla de tiers ya no es la vigente."""
    company = _company(db)
    db.add(MoatAssessment(
        company_id=company.id,
        moat_type="brand",
        strength=65,
        trend="stable",
        persistence="medium",
        confidence=0.6,
        status="evidence_backed",
        supporting_claim_ids=[1],
        contradicting_claim_ids=[],
        assessment_trace={"method": "MOAT_EVIDENCE_V1", "support_score": 1.6},
    ))
    db.commit()

    result = MoatService().read(db, company)
    assert [item["type"] for item in result["moats"]] == ["brand"]
    assert result["moats"][0]["policy"] == "superseded_policy"
    assert result["moats"][0]["evaluable"] is False
    # No se puede promediar un score cuya regla de fuentes ya no es la vigente.
    assert result["aggregate_strength"] is None
    assert result["status"] == STATUS_NOT_EVALUABLE
    assert result["aggregate"]["excluded_categories"] == [
        {
            "type": "brand",
            "status": "evidence_backed",
            "reason": "persisted_under_previous_scoring_policy",
        }
    ]