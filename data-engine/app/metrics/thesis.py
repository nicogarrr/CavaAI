"""Hit-rate de tesis: ¿acertaron? (#E5, metrica 3).

La pregunta solo tiene respuesta si la DEFINICION de acierto esta escrita antes
de mirar los numeros. Esta es, y es determinista (misma entrada, mismo
resultado):

UNIVERSO
    Una fila por ``ThesisVersion`` visible para el tenant. Se cuenta cada
    VERSION, no cada empresa: una tesis regenerada tres veces son tres
    opiniones y las tres se juzgaron con precios distintos. El coste es que una
    empresa muy regenerada pesa mas; se declara en ``definitions`` y el corte por
    decision permite renormalizar.

DIRECCION (rating -> signo)
    ``+1`` si ``rating == "attractive"``, ``-1`` si ``rating == "expensive"``: los
    dos valores que produce ``ThesisService._rating`` cuando hay margen de
    seguridad definido, o sea una opinion direccional real. Cualquier otro
    (``watch``, ``blocked``, ``incomplete_price``, ``insufficient_data``, o uno
    desconocido) NO es una apuesta direccional y se EXCLUYE con el motivo
    ``decision_neutra``: contarlo como fallo hundiria el hit-rate, y contarlo
    como acierto lo inflaria.

ENTRADA (regla de look-ahead)
    El PRIMER cierre con ``date >= fecha_de_publicacion``. La fecha de
    publicacion es ``ThesisVersion.created_at`` en UTC, que no cambia nunca
    (``updated_at`` si, y usarlo seria look-ahead puro: reescribir la tesis
    despues rebobinaria el punto de entrada). Nunca un precio anterior a la
    publicacion: comprar antes de que existiera la tesis no es prediccion.

    De cada par (entrada, salida) se usa UNA sola columna: ``adj_close`` si la
    serie tiene alguna, si no ``close``. Mezclar ajustadas y spot en la misma
    medicion esta descartado por construccion (ver ``_price_column``).

SALIDA
    El ultimo cierre con ``pub <= date <= pub + horizonte``. Si
    ``pub + horizonte`` es futuro -> ``demasiado_temprano``. Si no hay ningun
    precio en el rango -> ``sin_precio_salida``.

ACIERTO
    ``signo(direccion * retorno) > 0``. Retorno exactamente 0 -> ``empate``: sin
    movimiento no hay acierto ni fallo, y forzar uno de los dos lados seria
    escribir la respuesta.

NUMERADOR, DENOMINADOR Y EXCLUIDOS
    ``hits / evaluated``, con ``evaluated = hits + misses`` y un contador por
    cada motivo de exclusion, TODO en la misma fila. Un hit-rate sin
    denominador ni excluidos al lado es propaganda: es el fallo que ya se sufrio
    en otro punto del repo (``hit_rate 1.0`` sobre 14 celdas, marcado SOSPECHOSO).

ALPHA
    Retorno del benchmark (^GSPC, el mismo que usa ``market_regime_quant``) entre
    las MISMAS dos fechas, y solo sobre las tesis que tienen las dos piernas. Si
    falta la serie, ``alpha`` es ``None`` con motivo, nunca 0.

EVIDENCIA COMO DIMENSION
    El corte es el ``ThesisVersion.source_coverage_score`` que el repo YA
    persiste, en cuatro tramos. La celda ``(sector, tramo_evidence)`` es
    deliberada: si las tesis bien sourcing no acertan mas que las mal sourcing,
    esa es la metrica mas valiosa del conjunto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.metrics import config, stats
from app.models.entities import Company, MarketPrice, ThesisVersion
from app.models.metrics import ThesisHitRateCell

logger = logging.getLogger(__name__)

ANY = "*"
RATING_LONG = "compra"
RATING_SHORT = "venta"
DIRECTION_BY_RATING = {"attractive": 1, "expensive": -1}
UNKNOWN_SECTOR = "desconocido"
NO_BENCHMARK_REASON = "sin precios del benchmark para las fechas de la tesis"

EXCLUSION_REASONS = (
    "decision_neutra",
    "rating_desconocido",
    "sin_precio_entrada",
    "sin_precio_salida",
    "demasiado_temprano",
    "empate",
)


@dataclass
class ThesisOutcome:
    """El veredicto de UNA tesis en UN horizonte. Serializable y auditable."""

    thesis_version_id: int
    company_id: int
    ticker: str
    sector: str
    published_on: date
    horizon_days: int
    rating: str
    decision: str | None
    direction: int
    evidence_score: int | None
    evidence_bucket: str
    entry_date: date | None = None
    exit_date: date | None = None
    return_pct: float | None = None
    benchmark_return_pct: float | None = None
    hit: bool | None = None
    excluded: str | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class _Cell:
    hits: int = 0
    misses: int = 0
    excluded: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(EXCLUSION_REASONS, 0)
    )
    returns: list[float] = field(default_factory=list)
    paired_returns: list[float] = field(default_factory=list)
    paired_benchmarks: list[float] = field(default_factory=list)
    without_benchmark: int = 0

    @property
    def evaluated(self) -> int:
        return self.hits + self.misses

    def absorb(self, outcome: ThesisOutcome) -> None:
        if outcome.excluded:
            self.excluded[outcome.excluded] = self.excluded.get(outcome.excluded, 0) + 1
            return
        if outcome.hit:
            self.hits += 1
        else:
            self.misses += 1
        if outcome.return_pct is not None:
            self.returns.append(outcome.return_pct)
        if outcome.benchmark_return_pct is None:
            self.without_benchmark += 1
        elif outcome.return_pct is not None:
            self.paired_returns.append(outcome.return_pct)
            self.paired_benchmarks.append(outcome.benchmark_return_pct)

    @property
    def mean_return(self) -> float | None:
        return sum(self.returns) / len(self.returns) if self.returns else None


def evidence_bucket(score: int | None) -> str:
    if score is None:
        return "desconocido"
    if score <= 25:
        return "0-25"
    if score <= 50:
        return "26-50"
    if score <= 75:
        return "51-75"
    return "76-100"


def direction_for(rating: str | None) -> tuple[int, str, str | None]:
    """(direccion, etiqueta de decision, motivo de exclusion o None)."""
    key = (rating or "").strip().lower()
    if key in DIRECTION_BY_RATING:
        direction = DIRECTION_BY_RATING[key]
        return direction, (RATING_LONG if direction > 0 else RATING_SHORT), None
    if not key:
        return 0, ANY, "rating_desconocido"
    return 0, ANY, "decision_neutra"


def published_date(version: ThesisVersion) -> date:
    created = getattr(version, "created_at", None)
    if created is None:
        raise ValueError(f"thesis_version {version.id} sin created_at")
    if created.tzinfo is not None:
        created = created.astimezone(UTC).replace(tzinfo=None)
    return created.date()


def _price_column(rows: list[MarketPrice]) -> str:
    """`adj_close` si la serie tiene alguna; si no `close`. Nunca se mezclan.

    `MarketPrice.adj_close` es NULL cuando la fuente dio un spot y no una serie
    ajustada (lo dice el propio modelo). Comparar una entrada ajustada con una
    salida spot fabrica un retorno que no existe, asi que la decision se toma
    una sola vez por serie y se aplica a los dos extremos.
    """
    return "adj_close" if any(row.adj_close is not None for row in rows) else "close"


def _series(db: Session, company_id: int, start: date, end: date) -> list[MarketPrice]:
    return list(
        db.scalars(
            select(MarketPrice)
            .where(
                MarketPrice.company_id == company_id,
                MarketPrice.date >= start,
                MarketPrice.date <= end,
            )
            .order_by(MarketPrice.date)
        ).all()
    )


def _value(row: MarketPrice, column: str) -> float | None:
    raw: Decimal | None = getattr(row, column)
    return None if raw is None else float(raw)


def _return_pct(entry: float, exit_: float) -> float:
    return 0.0 if entry == 0 else (exit_ / entry - 1.0) * 100.0


def evaluate_thesis(
    db: Session,
    version: ThesisVersion,
    *,
    horizon_days: int,
    as_of: date,
    benchmark_company_id: int | None,
    sectors: dict[int, str],
    tickers: dict[int, str],
) -> ThesisOutcome:
    """Veredicto de una tesis en un horizonte. Determinista y sin look-ahead."""
    published = published_date(version)
    direction, decision, excluded = direction_for(version.rating)
    outcome = ThesisOutcome(
        thesis_version_id=version.id,
        company_id=version.company_id,
        ticker=tickers.get(version.company_id, ""),
        sector=sectors.get(version.company_id, UNKNOWN_SECTOR),
        published_on=published,
        horizon_days=horizon_days,
        rating=version.rating or "",
        decision=None if decision == ANY else decision,
        direction=direction,
        evidence_score=version.source_coverage_score,
        evidence_bucket=evidence_bucket(version.source_coverage_score),
        excluded=excluded,
    )
    if excluded:
        return outcome
    target = published + timedelta(days=horizon_days)
    rows = _series(db, version.company_id, published, min(target, as_of))
    if not rows:
        outcome.excluded = "sin_precio_entrada"
        return outcome
    if target > as_of:
        # El horizonte todavia no ha ocurrido. Se excluye aunque haya precios
        # parciales: evaluar a mitad de camino y llamarlo hit-rate es como se
        # fabrica un 100 %.
        outcome.excluded = "demasiado_temprano"
        return outcome
    column = _price_column(rows)
    usable = [(row, value) for row in rows if (value := _value(row, column)) is not None]
    if not usable:
        outcome.excluded = "sin_precio_entrada"
        return outcome
    entry_row, entry = usable[0]
    exit_row, exit_ = usable[-1]
    if exit_row.date <= entry_row.date:
        outcome.excluded = "sin_precio_salida"
        return outcome
    outcome.entry_date = entry_row.date
    outcome.exit_date = exit_row.date
    outcome.return_pct = _return_pct(entry, exit_)
    if outcome.return_pct == 0.0:
        outcome.excluded = "empate"
        return outcome
    outcome.hit = direction * outcome.return_pct > 0
    outcome.benchmark_return_pct = _benchmark_return(
        db, benchmark_company_id, entry_row.date, exit_row.date
    )
    return outcome


def _benchmark_return(
    db: Session, benchmark_company_id: int | None, start: date, end: date
) -> float | None:
    """Retorno del benchmark entre las MISMAS dos fechas de la tesis."""
    if benchmark_company_id is None:
        return None
    rows = _series(db, benchmark_company_id, start, end)
    if not rows:
        return None
    column = _price_column(rows)
    values = [value for value in (_value(row, column) for row in rows) if value is not None]
    if len(values) < 2 or values[0] == 0:
        return None
    return _return_pct(values[0], values[-1])


def _slices(outcome: ThesisOutcome) -> list[tuple[str, str, str]]:
    """Las cinco familias de corte que se emiten para cada tesis.

    `decision` es la dimension especial: una tesis neutra no tiene decision, y
    meterla en la celda `compra` como fallo falsearia el hit-rate por decision.
    Sale con `*` y su exclusion queda visible en la celda global.

    Se deduplican las claves: para una tesis neutra la celda global aparece dos
    veces en la lista (una por la familia "total" y otra por la de "decision"), y
    sin deduplicar cada exclusion se contaria dos veces. El `order` mantiene la
    familia global en su posicion natural.
    """
    decision = outcome.decision or ANY
    slices = [
        (ANY, ANY, ANY),
        (decision, ANY, ANY),
        (ANY, outcome.sector, ANY),
        (ANY, ANY, outcome.evidence_bucket),
        (ANY, outcome.sector, outcome.evidence_bucket),
    ]
    return list(dict.fromkeys(slices))


def compute_hit_rate(
    db: Session,
    *,
    as_of: date | None = None,
    horizons: tuple[int, ...] | None = None,
) -> tuple[list[ThesisHitRateCell], list[ThesisOutcome], dict]:
    """Recalcula las celdas de hit-rate del tenant de la sesion.

    Pesado por naturaleza (une precios, tesis y benchmark), asi que lo llama la
    tarea programada `refresh_backend_metrics`, NO un endpoint: un endpoint que
    hiciera esto en cada request quemaria la base de produccion.
    """
    today = as_of or datetime.now(UTC).date()
    horizon_list = horizons or config.hit_rate_horizons()
    versions = list(db.scalars(select(ThesisVersion)).all())
    sectors, tickers = _company_index(db, {version.company_id for version in versions})
    benchmark_company_id = _benchmark_company_id(db)
    cells: dict[tuple[int, str, str, str], _Cell] = {}
    outcomes: list[ThesisOutcome] = []
    for horizon in horizon_list:
        for version in versions:
            outcome = evaluate_thesis(
                db,
                version,
                horizon_days=horizon,
                as_of=today,
                benchmark_company_id=benchmark_company_id,
                sectors=sectors,
                tickers=tickers,
            )
            outcomes.append(outcome)
            for key in _slices(outcome):
                cells.setdefault((horizon, *key), _Cell()).absorb(outcome)
    definitions = hit_rate_definitions(today, horizon_list, benchmark_company_id)
    rows = [
        _to_row(cell, key, today, definitions, benchmark_company_id)
        for key, cell in cells.items()
    ]
    _replace_day(db, rows, today)
    return rows, outcomes, definitions


def _company_index(db: Session, company_ids: set[int]) -> tuple[dict[int, str], dict[int, str]]:
    """Sector y ticker por empresa. `companies` es maestra global, no de tenant."""
    if not company_ids:
        return {}, {}
    rows = db.execute(
        select(Company.id, Company.sector, Company.ticker).where(Company.id.in_(company_ids))
    ).all()
    sectors = {row[0]: (row[1] or UNKNOWN_SECTOR).strip() or UNKNOWN_SECTOR for row in rows}
    return sectors, {row[0]: row[2] for row in rows}


def _benchmark_company_id(db: Session) -> int | None:
    """El ^GSPC del propio repo, o None si no existe (no se inventa uno)."""
    return db.scalar(select(Company.id).where(Company.ticker == config.benchmark_ticker()))


def benchmark_company_id(db: Session) -> int | None:
    """Id del indice de referencia, o None si la base no lo tiene."""
    return _benchmark_company_id(db)


def _to_row(
    cell: _Cell,
    key: tuple[int, str, str, str],
    as_of: date,
    definitions: dict,
    benchmark_company_id: int | None,
) -> ThesisHitRateCell:
    horizon, decision, sector, evidence = key
    evaluated = cell.evaluated
    ordered = sorted(cell.returns)
    if evaluated and cell.paired_returns:
        alpha = (
            sum(cell.paired_returns) / len(cell.paired_returns)
            - sum(cell.paired_benchmarks) / len(cell.paired_benchmarks)
        )
        bench_status = "ok"
        bench_reason = None
    elif benchmark_company_id is None:
        alpha = None
        bench_status = "N/D"
        bench_reason = f"no hay empresa con ticker {config.benchmark_ticker()} en la base"
    else:
        alpha = None
        bench_status = "N/D"
        bench_reason = NO_BENCHMARK_REASON
    return ThesisHitRateCell(
        as_of=as_of,
        horizon_days=horizon,
        decision=decision,
        sector=sector,
        evidence_bucket=evidence,
        hits=cell.hits,
        misses=cell.misses,
        evaluated=evaluated,
        excluded_neutral=cell.excluded.get("decision_neutra", 0),
        excluded_rating_unknown=cell.excluded.get("rating_desconocido", 0),
        excluded_no_entry_price=cell.excluded.get("sin_precio_entrada", 0),
        excluded_no_exit_price=cell.excluded.get("sin_precio_salida", 0),
        excluded_too_early=cell.excluded.get("demasiado_temprano", 0),
        excluded_tie=cell.excluded.get("empate", 0),
        excluded_no_benchmark=cell.without_benchmark,
        hit_rate=(cell.hits / evaluated) if evaluated else None,
        avg_return=cell.mean_return,
        median_return=stats.percentile(ordered, 0.50),
        p10_return=stats.percentile(ordered, 0.10),
        p90_return=stats.percentile(ordered, 0.90),
        benchmark_ticker=config.benchmark_ticker() if benchmark_company_id else None,
        benchmark_return=(
            sum(cell.paired_benchmarks) / len(cell.paired_benchmarks)
            if cell.paired_benchmarks
            else None
        ),
        alpha=alpha,
        benchmark_status=bench_status,
        benchmark_reason=bench_reason,
        definitions=definitions,
        computed_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _replace_day(db: Session, rows: list[ThesisHitRateCell], as_of: date) -> None:
    """Idempotente: recalcular un dia replaces sus celdas, no las apila."""
    db.execute(delete(ThesisHitRateCell).where(ThesisHitRateCell.as_of == as_of))
    db.add_all(rows)
    db.commit()


def hit_rate_definitions(
    as_of: date, horizons: tuple[int, ...], benchmark_company_id: int | None
) -> dict:
    """El contrato con el lector, persistido junto a cada celda."""
    return {
        "version": 1,
        "as_of": as_of.isoformat(),
        "universo": "una fila por ThesisVersion visible para el tenant (no por empresa)",
        "fecha_publicacion": "ThesisVersion.created_at en UTC (nunca updated_at)",
        "direccion": {
            "+1": "rating == 'attractive'",
            "-1": "rating == 'expensive'",
            "excluida": "cualquier otro rating (decision_neutra / rating_desconocido)",
        },
        "entrada": "primer cierre con date >= fecha de publicacion; nunca un precio anterior",
        "columna_precio": "adj_close si la serie tiene alguna, si no close; nunca se mezclan",
        "salida": "ultimo cierre con pub <= date <= pub + horizonte",
        "acierto": "signo(direccion * retorno) > 0; retorno == 0 se excluye como empate",
        "denominador": "evaluated = hits + misses",
        "excluidos": list(EXCLUSION_REASONS),
        "horizontes_dias": list(horizons),
        "benchmark": config.benchmark_ticker() if benchmark_company_id is not None else None,
        "alpha": "retorno medio de las tesis con AMBAS piernas menos el retorno medio del "
                 "benchmark en las mismas fechas; None con motivo si falta la pierna",
    }


def hit_rate_payload(row: ThesisHitRateCell) -> dict:
    """Payload de API. Un hit-rate sin denominador ni excluidos no sale de aqui."""
    excluded = {
        "decision_neutra": row.excluded_neutral,
        "rating_desconocido": row.excluded_rating_unknown,
        "sin_precio_entrada": row.excluded_no_entry_price,
        "sin_precio_salida": row.excluded_no_exit_price,
        "demasiado_temprano": row.excluded_too_early,
        "empate": row.excluded_tie,
    }
    excluded_total = sum(excluded.values())
    if row.evaluated > 0:
        hit_rate = stats.disponible(row.hit_rate)
    else:
        hit_rate = stats.indisponible(
            "ninguna tesis con decision direccional tiene todas las fechas del horizonte; "
            f"excluidas: {excluded_total} ({excluded})"
        )
    sampled = stats.indisponible("sin tesis evaluadas")
    alpha_block = (
        stats.disponible(row.alpha)
        if row.benchmark_status == "ok" and row.alpha is not None
        else stats.indisponible(row.benchmark_reason or "sin benchmark configurado")
    )
    return {
        "as_of": row.as_of.isoformat(),
        "horizonte_dias": row.horizon_days,
        "decision": row.decision,
        "sector": row.sector,
        "calidad_evidencia": row.evidence_bucket,
        "numerador_aciertos": row.hits,
        "denominador_evaluados": row.evaluated,
        "fallos": row.misses,
        "excluidos": excluded,
        "excluidos_total": excluded_total,
        "excluidos_sin_benchmark": row.excluded_no_benchmark,
        "hit_rate": hit_rate,
        "retorno_medio": stats.disponible(row.avg_return) if row.avg_return is not None
        else dict(sampled),
        "retorno_mediano": stats.disponible(row.median_return)
        if row.median_return is not None else dict(sampled),
        "retorno_p10": stats.disponible(row.p10_return) if row.p10_return is not None
        else dict(sampled),
        "retorno_p90": stats.disponible(row.p90_return) if row.p90_return is not None
        else dict(sampled),
        "benchmark": row.benchmark_ticker,
        "retorno_benchmark": stats.disponible(row.benchmark_return)
        if row.benchmark_return is not None
        else stats.indisponible(row.benchmark_reason or "sin benchmark"),
        "alpha_vs_benchmark": alpha_block,
        "definiciones": row.definitions or {},
        "calculado_en": row.computed_at.isoformat() if row.computed_at else None,
    }


def cells_for(
    db: Session, *, as_of: date, horizon: int | None = None, limit: int = 200, offset: int = 0
) -> tuple[list[ThesisHitRateCell], int]:
    statement = select(ThesisHitRateCell).where(ThesisHitRateCell.as_of == as_of)
    if horizon is not None:
        statement = statement.where(ThesisHitRateCell.horizon_days == horizon)
    total = int(
        db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    rows = list(
        db.scalars(
            statement.order_by(
                ThesisHitRateCell.horizon_days,
                ThesisHitRateCell.decision,
                ThesisHitRateCell.sector,
                ThesisHitRateCell.evidence_bucket,
            )
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return rows, total


def source_auditor_breakdown(db: Session) -> dict:
    """Lo que el SourceAuditor ha bloqueado de verdad, en CONTADORES.

    Los textos de los claims no se tocan: son contenido de usuario y esta es una
    tabla de agregados. Solo cuantos, y cuantos de esos claims son materiales.
    """
    from app.models.entities import SourceAudit

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
    passed = sum(1 for row in rows if row[0])
    unsupported = sum(len(row[2] or []) for row in rows)
    weak = sum(len(row[3] or []) for row in rows)
    conflicts = sum(len(row[4] or []) for row in rows)
    fixes = sum(len(row[5] or []) for row in rows)
    scores = [float(row[1] or 0) for row in rows]
    return {
        "auditorias": total,
        "auditorias_pasadas": passed,
        "auditorias_fallidas": total - passed,
        "claims_sin_soporte": unsupported,
        "claims_debiles": weak,
        "conflictos_datos": conflicts,
        "fixes_requeridos": fixes,
        "cobertura_auditor_media": (sum(scores) / len(scores)) if scores else None,
    }