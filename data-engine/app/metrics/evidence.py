"""% de claims con evidencia, con DISTRIBUCION (#E5, metrica 4).

De donde sale, sin inventar un campo:

- **Claims**: filas de ``claims`` del tenant. Un claim es MATERIAL si
  ``materiality_score >= 7``, que es el corte que el propio repo ya fija en
  ``claim_scope`` ("un claim con materiality_score >= 7 y sin evidencia cuesta 8
  puntos").
- **Con evidencia**: al menos una fila en ``claim_evidence``. Que exista la fila
  ES la evidencia; la calidad se mide aparte.
- **Fuente verificada (OFICIAL) vs inferida**: se reutiliza la jerarquia del
  repo. ``ClaimEvidence.source_tier`` en ``tier_1_regulatory`` o
  ``tier_2_company`` es OFICIAL (el mismo criterio con el que
  ``materiality_service`` puntua); ademas se acepta un ``source_url`` en los
  hosts que ``thesis_provenance.OFFICIAL_HOSTS`` declara. Todo lo demas es
  INFERIDO.
- **Tesis**: ``ThesisVersion.source_coverage_score``, la columna que las tesis YA
  persisten. Su distribucion se reporta al lado de la calculada aqui, para poder
  ver si las dos cuentan lo mismo.

**Por que la distribucion y no la media.** Si el 90 % de las tesis tiene 100 % de
cobertura y el 10 % tiene 0 %, la media de 90 % no describe a nadie: describe la
suma de dos poblaciones. Por eso van p10/p50/p90 y un histograma de 8 tramos. Un
histograma con toda la masa en una sola barra es, en si mismo, el hallazgo.

**El breakdown del SourceAuditor son contadores, no textos.**
``unsupported_claims`` es una lista de enunciados de claim, y un enunciado es
contenido de usuario: no entra en una tabla de agregados. Se cuenta cuantos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import urlparse

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.metrics import config, stats
from app.models.entities import (
    Claim,
    ClaimEvidence,
    Company,
    SourceAudit,
    ThesisVersion,
)
from app.models.metrics import EvidenceCoverageSnapshot

OFFICIAL_TIERS = frozenset({"tier_1_regulatory", "tier_2_company"})
UNKNOWN_SECTOR = "desconocido"

# 8 tramos: el primero es el 0 exacto (una tesis sin una sola evidencia), que es
# un estado cualitativamente distinto de "casi todo".
COVERAGE_BUCKETS: tuple[str, ...] = ("0", "1-10", "11-25", "26-50", "51-75",
                                     "76-90", "91-99", "100")


def official_hosts() -> frozenset[str]:
    """Los hosts oficiales que declara el repo, leidos (no redefinidos) aqui."""
    try:
        from app.services.thesis_provenance import OFFICIAL_HOSTS

        return OFFICIAL_HOSTS
    except Exception:  # noqa: BLE001 — sin ese modulo, manda la jerarquia de tiers
        return frozenset()


def is_official(tier: str | None, url: str | None) -> bool:
    """OFICIAL si el tier lo dice, o si la URL es de un host oficial."""
    if (tier or "").strip() in OFFICIAL_TIERS:
        return True
    raw = (url or "").strip().lower()
    if not raw:
        return False
    host = (urlparse(raw).hostname or "").lower()
    hosts = official_hosts()
    return bool(host) and any(host == item or host.endswith(f".{item}") for item in hosts)


def is_official_evidence(evidence: ClaimEvidence) -> bool:
    return is_official(evidence.source_tier, evidence.source_url)


def coverage_bucket(pct: float) -> str:
    if pct <= 0:
        return "0"
    if pct <= 10:
        return "1-10"
    if pct <= 25:
        return "11-25"
    if pct <= 50:
        return "26-50"
    if pct <= 75:
        return "51-75"
    if pct <= 90:
        return "76-90"
    if pct < 100:
        return "91-99"
    return "100"


def coverage_histogram(values: list[float]) -> dict[str, int]:
    """Histograma de 8 tramos. Las claves ausentes son 0 explicito, no un hueco."""
    histogram: dict[str, int] = dict.fromkeys(COVERAGE_BUCKETS, 0)
    for value in values:
        histogram[coverage_bucket(value)] += 1
    return histogram


def _pct(numerator: int, denominator: int) -> float | None:
    """Porcentaje, o None si no hay denominador. Nunca 0 de relleno."""
    return None if denominator <= 0 else 100.0 * numerator / denominator


def _claim_evidence_index(db: Session, claim_ids: list[int]) -> dict[int, dict[str, bool]]:
    """Por claim: {tiene_evidencia, oficial}. Dos consultas, no N+1.

    La deteccion de OFICIAL por URL se hace en Python a proposito: pedirle a SQL
    que compare el host de una URL con una lista es un `LIKE` por host y por
    fila, y el numero de claims materiales de un tenant cabe de sobra en memoria.
    """
    if not claim_ids:
        return {}
    rows = db.execute(
        select(ClaimEvidence.claim_id, ClaimEvidence.source_tier, ClaimEvidence.source_url).where(
            ClaimEvidence.claim_id.in_(claim_ids)
        )
    ).all()
    index: dict[int, dict[str, bool]] = {}
    for claim_id, tier, url in rows:
        entry = index.setdefault(int(claim_id), {"tiene_evidencia": False, "oficial": False})
        entry["tiene_evidencia"] = True
        entry["oficial"] = entry["oficial"] or is_official(tier, url)
    return index


def compute_evidence_coverage(
    db: Session, *, as_of: date | None = None, threshold: int | None = None
) -> EvidenceCoverageSnapshot:
    """Recalcula el snapshot de cobertura de evidencia del tenant de la sesion.

    La llama la tarea programada, no un endpoint: son agregaciones sobre claims,
    evidencias, auditorias y tesis, y eso no se recalcula por request.
    """
    today = as_of or datetime.now(UTC).date()
    cutoff = max(0, threshold if threshold is not None else config.materiality_threshold())
    claims = db.execute(
        select(
            Claim.id,
            Claim.thesis_version_id,
            Claim.materiality_score,
            Claim.company_id,
        )
    ).all()
    index = _claim_evidence_index(db, [int(row[0]) for row in claims])

    claims_total = len(claims)
    claims_with_evidence = sum(
        1 for row in claims if index.get(int(row[0]), {}).get("tiene_evidencia")
    )
    material_rows = [row for row in claims if int(row[2] or 0) >= cutoff]
    material_total = len(material_rows)
    material_with = 0
    material_official = 0
    per_version: dict[int, list[int]] = {}
    for row in material_rows:
        claim_id = int(row[0])
        flags = index.get(claim_id, {})
        bucket = per_version.setdefault(int(row[1] or 0), [0, 0])
        bucket[0] += 1
        if flags.get("tiene_evidencia"):
            bucket[1] += 1
            material_with += 1
            if flags.get("oficial"):
                material_official += 1
    coverages = [
        100.0 * with_ / total for total, with_ in per_version.values() if total > 0
    ]
    ordered_coverages = sorted(coverages)
    scores = sorted(
        float(value or 0) for (value,) in db.execute(
            select(ThesisVersion.source_coverage_score)
        ).all()
    )
    snapshot = EvidenceCoverageSnapshot(
        as_of=today,
        scope="global",
        claims_total=claims_total,
        claims_with_evidence=claims_with_evidence,
        material_claims=material_total,
        material_with_evidence=material_with,
        material_with_official=material_official,
        material_with_inferred=max(0, material_with - material_official),
        material_without_evidence=max(0, material_total - material_with),
        thesis_versions_considered=len(per_version),
        coverage_p10=stats.percentile(ordered_coverages, 0.10),
        coverage_p50=stats.percentile(ordered_coverages, 0.50),
        coverage_p90=stats.percentile(ordered_coverages, 0.90),
        coverage_mean=(sum(coverages) / len(coverages)) if coverages else None,
        coverage_histogram=coverage_histogram(coverages),
        score_p10=stats.percentile(scores, 0.10),
        score_p50=stats.percentile(scores, 0.50),
        score_p90=stats.percentile(scores, 0.90),
        score_histogram=coverage_histogram(scores),
        materiality_threshold=cutoff,
        computed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    for name, value in _auditor_breakdown(db).items():
        setattr(snapshot, name, value)
    _replace_day(db, snapshot, today)
    return snapshot


def _auditor_breakdown(db: Session) -> dict:
    """Contadores del SourceAuditor. Nunca los textos de los claims."""
    rows = db.execute(
        select(
            SourceAudit.passed,
            SourceAudit.source_coverage_score,
            SourceAudit.unsupported_claims,
            SourceAudit.weak_claims,
            SourceAudit.data_conflicts,
            SourceAudit.required_fixes,
        )
    ).all()
    total = len(rows)
    scores = [float(row[1] or 0) for row in rows]
    return {
        "audits_total": total,
        "audits_passed": sum(1 for row in rows if row[0]),
        "unsupported_total": sum(len(row[2] or []) for row in rows),
        "weak_total": sum(len(row[3] or []) for row in rows),
        "data_conflicts_total": sum(len(row[4] or []) for row in rows),
        "required_fixes_total": sum(len(row[5] or []) for row in rows),
        "auditor_mean_coverage": (sum(scores) / len(scores)) if scores else None,
    }


def _replace_day(db: Session, snapshot: EvidenceCoverageSnapshot, as_of: date) -> None:
    """Idempotente: recalcular un dia replaces su snapshot, no lo apila.

    El DELETE se Vacuum y a la BD ANTES del INSERT. SQLAlchemy hace flush del
    INSERT antes que del DELETE, asi que dejar las dos operaciones en el mismo
    flush revienta el UNIQUE (tenant_id, as_of, scope): la fila nueva entra antes
    de que salga la vieja.
    """
    existing = db.scalar(
        select(EvidenceCoverageSnapshot).where(
            EvidenceCoverageSnapshot.as_of == as_of,
            EvidenceCoverageSnapshot.scope == snapshot.scope,
        )
    )
    if existing is not None:
        db.delete(existing)
        db.flush()
    db.add(snapshot)
    db.commit()


def evidence_payload(snapshot: EvidenceCoverageSnapshot) -> dict:
    """Payload de API. La media siempre viaja con su distribucion al lado."""
    material = snapshot.material_claims
    material_block = (
        stats.disponible(100.0 * snapshot.material_with_evidence / material)
        if material > 0
        else stats.indisponible(
            f"no hay claims materiales (materiality_score >= {snapshot.materiality_threshold}) "
            "para este tenant"
        )
    )
    official_block = (
        stats.disponible(100.0 * snapshot.material_with_official / material)
        if material > 0
        else stats.indisponible("sin claims materiales")
    )
    all_claims_block = (
        stats.disponible(100.0 * snapshot.claims_with_evidence / snapshot.claims_total)
        if snapshot.claims_total > 0
        else stats.indisponible("el tenant no tiene claims en la ventana")
    )
    sin_tesis = stats.indisponible("ninguna tesis con claims materiales")
    auditor_mean = (
        stats.disponible(snapshot.auditor_mean_coverage)
        if snapshot.auditor_mean_coverage is not None
        else stats.indisponible("el SourceAuditor no ha corrido para este tenant")
    )
    return {
        "as_of": snapshot.as_of.isoformat(),
        "ambito": snapshot.scope,
        "materialidad_minima": snapshot.materiality_threshold,
        "claims_totales": snapshot.claims_total,
        "claims_con_evidencia_todos": all_claims_block,
        "claims_materiales": snapshot.material_claims,
        "materiales_con_evidencia": material_block,
        "materiales_con_fuente_oficial": official_block,
        "materiales_con_fuente_inferida": snapshot.material_with_inferred,
        "materiales_sin_evidencia": snapshot.material_without_evidence,
        "distribucion_por_tesis": {
            "tesis_consideradas": snapshot.thesis_versions_considered,
            "p10": _opt(snapshot.coverage_p10, sin_tesis),
            "p50": _opt(snapshot.coverage_p50, sin_tesis),
            "p90": _opt(snapshot.coverage_p90, sin_tesis),
            "media": _opt(snapshot.coverage_mean, sin_tesis),
            "histograma": snapshot.coverage_histogram or {},
            "lectura": "un histograma con toda la masa en una barra describe mas que la media",
        },
        "distribucion_source_coverage_score": {
            "p10": _opt(snapshot.score_p10, stats.indisponible("no hay thesis_versions")),
            "p50": _opt(snapshot.score_p50, stats.indisponible("no hay thesis_versions")),
            "p90": _opt(snapshot.score_p90, stats.indisponible("no hay thesis_versions")),
            "histograma": snapshot.score_histogram or {},
        },
        "source_auditor": {
            "auditorias": snapshot.audits_total,
            "pasadas": snapshot.audits_passed,
            "fallidas": max(0, snapshot.audits_total - snapshot.audits_passed),
            "claims_sin_soporte": snapshot.unsupported_total,
            "claims_debiles": snapshot.weak_total,
            "conflictos_datos": snapshot.data_conflicts_total,
            "fixes_requeridos": snapshot.required_fixes_total,
            "cobertura_media": auditor_mean,
            "nota": "contadores, nunca los textos de los claims (son contenido de usuario)",
        },
        "calculado_en": snapshot.computed_at.isoformat() if snapshot.computed_at else None,
    }


def _opt(value: float | None, nd: dict) -> dict:
    return stats.disponible(value) if value is not None else dict(nd)


def sector_breakdown(db: Session, threshold: int | None = None) -> dict:
    """Cobertura por sector. `companies` es maestra global, no dato de tenant."""
    cutoff = max(0, threshold if threshold is not None else config.materiality_threshold())
    material = case((Claim.materiality_score >= cutoff, 1), else_=0)
    evidenced = case((ClaimEvidence.id.is_not(None), 1), else_=0)
    rows = db.execute(
        select(Company.sector, material, evidenced, func.count(Claim.id))
        .select_from(Claim)
        .join(Company, Company.id == Claim.company_id)
        .outerjoin(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .group_by(Company.sector, material, evidenced)
    ).all()
    buckets: dict[str, dict[str, int]] = {}
    for sector, is_material, has_evidence, count in rows:
        name = (sector or UNKNOWN_SECTOR).strip() or UNKNOWN_SECTOR
        entry = buckets.setdefault(name, {"claims": 0, "materiales": 0, "materiales_con_evidencia": 0})
        entry["claims"] += int(count or 0)
        if int(is_material or 0) == 1:
            entry["materiales"] += int(count or 0)
            entry["materiales_con_evidencia"] += int(count or 0) if int(has_evidence or 0) == 1 else 0
    return {
        name: {
            **counts,
            "pct_materiales_con_evidencia": _pct(
                counts["materiales_con_evidencia"], counts["materiales"]
            ),
        }
        for name, counts in sorted(buckets.items())
    }


def latest_snapshot(
    db: Session, as_of: date | None = None
) -> EvidenceCoverageSnapshot | None:
    """Ultimo snapshot disponible hasta `as_of` (incluido)."""
    today = as_of or datetime.now(UTC).date()
    return db.scalar(
        select(EvidenceCoverageSnapshot)
        .where(
            EvidenceCoverageSnapshot.as_of <= today,
            EvidenceCoverageSnapshot.scope == "global",
        )
        .order_by(EvidenceCoverageSnapshot.as_of.desc())
        .limit(1)
    )