"""% de claims con evidencia: material vs total, oficial vs inferido,
distribucion y breakdown del SourceAuditor (#E5, metrica 4).

La prueba central de este fichero es la distribucion: si el 90 % de las tesis
tiene 100 % de cobertura y el 10 % tiene 0 %, la media de 90 % no describe a
nadie. Aqui se siembra exactamente esa poblacion bimodal y se comprueba que el
histograma la delata y que la media, sola, no dice nada.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.metrics import config, prometheus
from app.metrics import evidence as evidence_stats
from app.models.entities import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    SourceAudit,
    ThesisVersion,
)
from app.models.metrics import EvidenceCoverageSnapshot

TODAY = date(2026, 6, 30)
MATERIAL = config.materiality_threshold()


def _session(tenant_id: int | None = 1):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    if tenant_id is not None:
        session.info["tenant_id"] = tenant_id
    return session


def _company(session, ticker: str, sector: str = "Tecnologia") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector=sector, company_type="operating", valuation_model="dcf",
    )
    session.add(company)
    session.commit()
    return company


def _thesis(session, company: Company, coverage: int) -> ThesisVersion:
    siguiente = len(
        session.query(ThesisVersion).filter(ThesisVersion.company_id == company.id).all()
    ) + 1
    version = ThesisVersion(
        company_id=company.id, version=siguiente, status="final",
        thesis_markdown="# t", executive_summary="r", rating="attractive",
        source_coverage_score=coverage,
    )
    session.add(version)
    session.commit()
    return version


def _claim(session, version: ThesisVersion, statement: str, materiality: int) -> Claim:
    claim = Claim(
        company_id=version.company_id,
        thesis_version_id=version.id,
        statement=statement,
        claim_type="thesis",
        status="verified",
        materiality_score=materiality,
        source_quality="primary",
    )
    session.add(claim)
    session.commit()
    return claim


def _evidence(session, claim: Claim, *, tier: str = "secondary",
              url: str | None = None, document: Document | None = None) -> ClaimEvidence:
    row = ClaimEvidence(
        claim_id=claim.id,
        document_id=document.id if document else None,
        source_url=url,
        evidence_type="supports",
        summary="resumen de la evidencia",
        confidence=0.8,
        source_tier=tier,
    )
    session.add(row)
    session.commit()
    return row


# --- oficial vs inferido -----------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "url", "esperado"),
    [
        ("tier_1_regulatory", None, True),
        ("tier_2_company", None, True),
        ("tier_3_transcript", None, False),
        ("tier_5_data_provider", None, False),
        ("secondary", "https://www.sec.gov/Archives/edgar/x.htm", True),
        ("secondary", "https://blog.ejemplo.com/post", False),
        ("secondary", None, False),
        (None, "https://www.sec.gov/x", True),
        (None, "no-es-una-url", False),
        # Un host que solo CONTIENE "sec.gov" no es un host oficial.
        ("secondary", "https://sec.gov.falso.example/x", False),
    ],
)
def test_oficial_se_reusa_la_jerarquia_del_repo(tier, url, esperado):
    assert evidence_stats.is_official(tier, url) is esperado


def test_los_hosts_oficiales_vienen_del_repo_no_de_una_copia():
    from app.services.thesis_provenance import OFFICIAL_HOSTS

    assert evidence_stats.official_hosts() == OFFICIAL_HOSTS
    assert "www.sec.gov" in evidence_stats.official_hosts()


# --- materialidad: el corte es el del repo ----------------------------------


def test_el_corte_de_materialidad_es_el_que_ya_fija_claim_scope():
    # `claim_scope` dice: "un claim con materiality_score >= 7 y sin evidencia
    # cuesta 8 puntos". Reutilizar ese corte y no inventar otro.
    assert MATERIAL == 7


def test_los_claims_no_materiales_no_entran_en_el_porcentaje():
    session = _session()
    company = _company(session, "NMAT")
    version = _thesis(session, company, 100)
    material = _claim(session, version, "el margen bruto cae", 9)
    menor = _claim(session, version, "el CEO fue a una conference", 2)
    _evidence(session, material)
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.material_claims == 1
    assert snapshot.material_with_evidence == 1
    assert snapshot.claims_total == 2
    assert snapshot.claims_with_evidence == 1
    assert material.id != menor.id


# --- porcentajes y N/D ------------------------------------------------------


def test_el_porcentaje_de_materiales_con_evidencia():
    session = _session()
    company = _company(session, "PCT")
    version = _thesis(session, company, 100)
    for index in range(4):
        claim = _claim(session, version, f"claim {index}", 8)
        if index < 3:
            _evidence(session, claim)
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.material_claims == 4
    assert snapshot.material_with_evidence == 3
    assert snapshot.material_without_evidence == 1
    payload = evidence_stats.evidence_payload(snapshot)
    assert payload["materiales_con_evidencia"]["valor"] == pytest.approx(75.0)


def test_sin_claims_el_porcentaje_es_nd_no_cero():
    session = _session()
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    payload = evidence_stats.evidence_payload(snapshot)
    assert snapshot.claims_total == 0
    assert payload["materiales_con_evidencia"]["estado"] == "N/D"
    assert payload["materiales_con_evidencia"]["valor"] is None
    assert "materiality_score" in payload["materiales_con_evidencia"]["motivo"]
    # Un 0 aqui seria "el 0 % de los claims tiene evidencia", que es distinto.
    assert payload["materiales_con_evidencia"]["valor"] != 0


def test_el_corte_de_materialidad_es_configurable():
    session = _session()
    company = _company(session, "THR")
    version = _thesis(session, company, 100)
    _claim(session, version, "median", 5)
    _claim(session, version, "grande", 9)
    _evidence(session, session.scalar(select(Claim).where(Claim.materiality_score == 9)))
    con_siete = evidence_stats.compute_evidence_coverage(session, as_of=TODAY, threshold=7)
    assert con_siete.material_claims == 1
    con_cero = evidence_stats.compute_evidence_coverage(session, as_of=TODAY, threshold=0)
    assert con_cero.material_claims == 2


# --- oficial vs inferido en el agregado -------------------------------------


def test_el_snapshot_separa_oficial_de_inferido():
    session = _session()
    company = _company(session, "OFICIAL")
    version = _thesis(session, company, 100)
    con_regulatorio = _claim(session, version, "10-K: ingresos +8 %", 9)
    con_ir = _claim(session, version, "IR slide: guidance alza", 8)
    con_prensa = _claim(session, version, "noticia de prensa", 9)
    _evidence(session, con_regulatorio, tier="tier_1_regulatory")
    _evidence(session, con_ir, tier="tier_2_company")
    _evidence(session, con_prensa, tier="tier_4_reputable_media",
             url="https://www.reuters.com/x")
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.material_claims == 3
    assert snapshot.material_with_evidence == 3
    assert snapshot.material_with_official == 2
    assert snapshot.material_with_inferred == 1
    payload = evidence_stats.evidence_payload(snapshot)
    assert payload["materiales_con_fuente_oficial"]["valor"] == pytest.approx(200 / 3)


def test_un_claim_con_una_evidencia_oficial_entre_dos_inferidas_cuenta_como_oficial():
    session = _session()
    company = _company(session, "MIXTIER")
    version = _thesis(session, company, 100)
    claim = _claim(session, version, "dato con fuentes mixtas", 9)
    _evidence(session, claim, tier="tier_4_reputable_media", url="https://reuters.com/x")
    _evidence(session, claim, tier="tier_1_regulatory")
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.material_with_evidence == 1
    assert snapshot.material_with_official == 1
    assert snapshot.material_with_inferred == 0


# --- LA distribucion, que es el punto ---------------------------------------


def test_la_media_70_por_ciento_es_una_mentira_y_el_histograma_lo_demuestra():
    session = _session()
    # 7 tesis con cobertura 100 % y 3 con cobertura 0 %: media = 70 %.
    for index in range(7):
        company = _company(session, f"BIM{index}")
        version = _thesis(session, company, 100)
        for claim_index in range(4):
            claim = _claim(session, version, f"claim {claim_index}", 9)
            _evidence(session, claim, tier="tier_1_regulatory")
    for index in range(3):
        floja = _company(session, f"BIMFLOJA{index}")
        floja_version = _thesis(session, floja, 0)
        for claim_index in range(4):
            _claim(session, floja_version, f"sin soporte {claim_index}", 9)

    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.thesis_versions_considered == 10
    assert snapshot.coverage_mean == pytest.approx(70.0)
    histograma = snapshot.coverage_histogram
    assert histograma["100"] == 7
    assert histograma["0"] == 3
    # El 70 % no describe a ninguna tesis: tres no tienen ni una evidencia y
    # siete la tienen para todo. Solo la distribucion dice eso.
    assert snapshot.coverage_p10 == pytest.approx(0.0)
    assert snapshot.coverage_p50 == pytest.approx(100.0)
    assert snapshot.coverage_p90 == pytest.approx(100.0)
    assert snapshot.coverage_mean < snapshot.coverage_p50
    payload = evidence_stats.evidence_payload(snapshot)
    assert payload["distribucion_por_tesis"]["histograma"]["0"] == 3
    assert payload["distribucion_por_tesis"]["histograma"]["100"] == 7
    assert "histograma" in payload["distribucion_por_tesis"]


@pytest.mark.parametrize(
    ("pct", "tramo"),
    [
        (0.0, "0"), (0.1, "1-10"), (10.0, "1-10"), (10.1, "11-25"), (25.0, "11-25"),
        (50.0, "26-50"), (75.0, "51-75"), (90.0, "76-90"), (99.9, "91-99"),
        (100.0, "100"),
    ],
)
def test_los_tramos_del_histograma(pct, tramo):
    assert evidence_stats.coverage_bucket(pct) == tramo


def test_el_histograma_tiene_los_ocho_tramos_siempre_en_0():
    # Un histograma con las claves ausentes obliga al lector a distinguir "0 en
    # este tramo" de "este tramo no existe".
    histograma = evidence_stats.coverage_histogram([100.0])
    assert set(histograma) == set(evidence_stats.COVERAGE_BUCKETS)
    assert all(valor >= 0 for valor in histograma.values())
    assert histograma["0"] == 0
    assert histograma["100"] == 1


def test_sin_tesis_la_distribucion_es_nd():
    session = _session()
    company = _company(session, "SINMAT")
    version = _thesis(session, company, 100)
    _claim(session, version, "no material", 1)
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    payload = evidence_stats.evidence_payload(snapshot)
    assert snapshot.thesis_versions_considered == 0
    assert payload["distribucion_por_tesis"]["p50"]["estado"] == "N/D"
    assert payload["distribucion_por_tesis"]["media"]["estado"] == "N/D"


def test_la_distribucion_del_score_persistido_viene_de_las_tesis():
    session = _session()
    for index, score in enumerate((100, 90, 40, 0)):
        company = _company(session, f"SCR{index}")
        _thesis(session, company, score)
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.score_p10 < snapshot.score_p50 < snapshot.score_p90
    assert snapshot.score_histogram["100"] == 1
    assert snapshot.score_histogram["0"] == 1
    assert snapshot.score_histogram["76-90"] == 1
    payload = evidence_stats.evidence_payload(snapshot)
    assert payload["distribucion_source_coverage_score"]["histograma"]["0"] == 1


# --- breakdown del SourceAuditor --------------------------------------------


def test_el_breakdown_del_auditor_son_contadores_no_textos():
    session = _session()
    company = _company(session, "AUDIT")
    version = _thesis(session, company, 60)
    # Texto de claim deliberadamente con PII: es contenido de usuario y no debe
    # aparecer en ninguna tabla de agregados.
    session.add(
        SourceAudit(
            thesis_version_id=version.id,
            passed=False,
            source_coverage_score=40,
            unsupported_claims=["El cliente X pidio 3 M de deuda", "margen del 40 %"],
            weak_claims=["crecimiento sin fuente"],
            data_conflicts=["EBITDA 2025: 120 vs 90"],
            required_fixes=["Add source_id to every material claim."],
        )
    )
    session.commit()
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.audits_total == 1
    assert snapshot.audits_passed == 0
    assert snapshot.unsupported_total == 2
    assert snapshot.weak_total == 1
    assert snapshot.data_conflicts_total == 1
    assert snapshot.required_fixes_total == 1
    assert snapshot.auditor_mean_coverage == pytest.approx(40.0)
# Y nada de eso se ha copiado al snapshot: sus unicas columnas son
    # contadores y distribuciones.
    for nombre in EvidenceCoverageSnapshot.__table__.columns:
        assert "cliente X" not in str(snapshot.__dict__.get(nombre))


def test_sin_auditorias_la_media_del_auditor_es_nd():
    session = _session()
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    payload = evidence_stats.evidence_payload(snapshot)
    assert snapshot.audits_total == 0
    assert snapshot.auditor_mean_coverage is None
    assert payload["source_auditor"]["cobertura_media"]["estado"] == "N/D"


def test_el_auditor_bloquea_una_tesis_sin_soporte():
    # El motor de reglas del propio repo, para que el numero de metricas se
    # compare con la puerta que el producto ya pone.
    from app.services.source_auditor import SourceAuditor

    resultado = SourceAuditor().audit(
        [{"claim": "margen del 40 %", "material": True, "source_id": None}], {"engine": "dcf"}
    )
    assert resultado.passed is False
    assert resultado.source_coverage_score == 0
    assert resultado.unsupported_claims == ["margen del 40 %"]


# --- aislamiento por tenant -------------------------------------------------


def test_dos_tenants_no_ven_los_claims_del_otro():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def sembrar(tenant_id: int, ticker: str) -> None:
        session = factory()
        session.info["tenant_id"] = tenant_id
        company = _company(session, ticker)
        version = _thesis(session, company, 100)
        claim = _claim(session, version, f"claim de {ticker}", 9)
        _evidence(session, claim, tier="tier_1_regulatory")
        evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
        session.close()

    sembrar(1, "EV-ONE")
    sembrar(2, "EV-TWO")

    uno = factory()
    uno.info["tenant_id"] = 1
    filas_uno = list(uno.scalars(select(EvidenceCoverageSnapshot)).all())
    assert len(filas_uno) == 1
    assert filas_uno[0].claims_total == 1
    assert filas_uno[0].tenant_id == 1

    dos = factory()
    dos.info["tenant_id"] = 2
    filas_dos = list(dos.scalars(select(EvidenceCoverageSnapshot)).all())
    assert len(filas_dos) == 1
    assert filas_dos[0].tenant_id == 2


# --- idempotencia, por sector y prometheus -----------------------------------


def test_recalcular_el_mismo_dia_reemplaza_el_snapshot():
    session = _session()
    company = _company(session, "IDEM")
    version = _thesis(session, company, 100)
    _claim(session, version, "c", 9)
    evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert session.query(EvidenceCoverageSnapshot).count() == 1
    evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert session.query(EvidenceCoverageSnapshot).count() == 1


def test_el_breakdown_por_sector():
    session = _session()
    tech = _company(session, "SECTEC", sector="Tecnologia")
    salud = _company(session, "SECSAL", sector="Salud")
    for company, con_evidencia in ((tech, 2), (salud, 1)):
        version = _thesis(session, company, 100)
        for index in range(2):
            claim = _claim(session, version, f"{company.ticker}-{index}", 9)
            if index < con_evidencia:
                _evidence(session, claim, tier="tier_1_regulatory")
    breakdown = evidence_stats.sector_breakdown(session)
    assert breakdown["Tecnologia"]["materiales"] == 2
    assert breakdown["Tecnologia"]["materiales_con_evidencia"] == 2
    assert breakdown["Tecnologia"]["pct_materiales_con_evidencia"] == pytest.approx(100.0)
    assert breakdown["Salud"]["materiales_con_evidencia"] == 1
    assert breakdown["Salud"]["pct_materiales_con_evidencia"] == pytest.approx(50.0)


def test_prometheus_expone_el_histograma_y_no_un_cero_de_releno():
    session = _session()
    company = _company(session, "PROMEV")
    version = _thesis(session, company, 100)
    claim = _claim(session, version, "con evidencia", 9)
    _evidence(session, claim, tier="tier_1_regulatory")
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    texto = "\n".join(prometheus.evidence_metrics(snapshot, tenant_id=1))
    assert "cavaai_evidencia_pct_materiales" in texto
    assert 'tramo="100"' in texto
    assert "cavaai_evidencia_cobertura_tesis_bucket{" in texto
    assert "# TYPE cavaai_evidencia_cobertura_tesis_bucket gauge" in texto
    assert "no_medible" not in texto  # aqui si hay denominador para todo


def test_prometheus_marca_lo_no_medible_como_ausente():
    session = _session()
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    texto = "\n".join(prometheus.evidence_metrics(snapshot, tenant_id=1))
    assert "cavaai_evidencia_pct_materiales_no_medible" in texto
    assert "cavaai_evidencia_pct_materiales{" not in texto


def test_sin_snapshot_prometheus_no_emite_nada():
    assert prometheus.evidence_metrics(None, tenant_id=1) == []


def test_un_documento_no_convierte_un_claim_en_oficial():
    # La existencia de la fila ES la evidencia; su calidad la decide el tier o la
    # URL. Un `document_id` sin URL oficial no convierte nada en OFICIAL.
    session = _session()
    company = _company(session, "DOCONLY")
    version = _thesis(session, company, 100)
    document = Document(
        company_id=company.id, title="10-K", source_type="sec_edgar", source_url=None,
    )
    session.add(document)
    session.commit()
    claim = _claim(session, version, "con documento", 9)
    _evidence(session, claim, tier="secondary", document=document)
    snapshot = evidence_stats.compute_evidence_coverage(session, as_of=TODAY)
    assert snapshot.material_with_evidence == 1
    assert snapshot.material_with_official == 0
    assert snapshot.material_with_inferred == 1
    assert urlparse("https://x.example") is not None

# --- API --------------------------------------------------------------------


_schema_ready = False


def _ensure_schema() -> None:
    """Crea el esquema en la SQLite de la sesion (la de conftest, no una propia)."""
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import init_db

    init_db()
    _schema_ready = True


def _api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.metrics import router as metrics_router

    _ensure_schema()
    app = FastAPI()
    app.include_router(metrics_router, prefix="/api/metrics")
    return TestClient(app)


def test_el_endpoint_de_evidencia_sin_snapshot_devuelve_nd_no_ceros():
    cuerpo = _api_client().get(
        "/api/metrics/evidencia", params={"as_of": "2020-01-01"}
    ).json()
    assert cuerpo["metrica"] == "claims_con_evidencia"
    assert cuerpo["materiales_con_evidencia"]["estado"] == "N/D"
    assert cuerpo["materiales_con_evidencia"]["valor"] is None
    assert "refresh_backend_metrics" in cuerpo["materiales_con_evidencia"]["motivo"]
    assert cuerpo["distribucion_por_tesis"]["estado"] == "N/D"


def test_el_endpoint_de_evidencia_trae_el_snapshot_con_su_histograma():
    from app.core.database import SessionLocal

    _ensure_schema()
    db = SessionLocal()
    db.info["tenant_id"] = None
    try:
        db.add(
            EvidenceCoverageSnapshot(
                tenant_id=None, as_of=date.today(), scope="global",
                claims_total=10, claims_with_evidence=7, material_claims=10,
                material_with_evidence=7, material_with_official=5,
                material_with_inferred=2, material_without_evidence=3,
                thesis_versions_considered=4, coverage_p10=0.0, coverage_p50=50.0,
                coverage_p90=100.0, coverage_mean=70.0,
                coverage_histogram={"0": 1, "1-10": 0, "11-25": 0, "26-50": 1,
                                    "51-75": 0, "76-90": 0, "91-99": 0, "100": 2},
                score_p10=10.0, score_p50=60.0, score_p90=95.0,
                score_histogram={"0": 0, "1-10": 0, "11-25": 0, "26-50": 0,
                                 "51-75": 0, "76-90": 0, "91-99": 0, "100": 4},
                audits_total=4, audits_passed=2, unsupported_total=5, weak_total=3,
                data_conflicts_total=1, required_fixes_total=4,
                auditor_mean_coverage=55.0, materiality_threshold=7,
            )
        )
        db.commit()
    finally:
        db.close()

    cuerpo = _api_client().get("/api/metrics/evidencia").json()
    assert cuerpo["materiales_con_evidencia"]["valor"] == pytest.approx(70.0)
    assert cuerpo["materiales_con_fuente_oficial"]["valor"] == pytest.approx(50.0)
    assert cuerpo["materiales_con_fuente_inferida"] == 2
    assert cuerpo["materiales_sin_evidencia"] == 3
    # La media del 70 % con el histograma al lado: ahi se ve que hay tres
    # poblaciones, no una.
    assert cuerpo["distribucion_por_tesis"]["media"]["valor"] == pytest.approx(70.0)
    assert cuerpo["distribucion_por_tesis"]["histograma"]["0"] == 1
    assert cuerpo["distribucion_por_tesis"]["histograma"]["100"] == 2
    assert cuerpo["distribucion_por_tesis"]["p10"]["valor"] == pytest.approx(0.0)
    assert cuerpo["source_auditor"]["auditorias"] == 4
    assert cuerpo["source_auditor"]["claims_sin_soporte"] == 5
    assert cuerpo["source_auditor"]["conflictos_datos"] == 1
    assert "contadores" in cuerpo["source_auditor"]["nota"]
    assert cuerpo["retencion_dias"] == config.retention_days("evidence_coverage_snapshots")


def test_el_resumen_incluye_las_cuatro_metricas_con_su_tenant():
    _ensure_schema()
    cuerpo = _api_client().get("/api/metrics/resumen").json()
    assert cuerpo["tenant"]["id"] is None
    assert "aislado_por" in cuerpo["tenant"]
    assert set(cuerpo) >= {"latencia", "cola", "hit_rate", "evidencia"}
    assert cuerpo["cola"]["colas"] >= 0
