"""D3: la tesis contra lo que pasó. Retorno realizado y veredicto.

Este servicio cierra el bucle de la memoria de inversor. Hoy se guarda la
tesis y se guarda la lección, pero nada las une al resultado: se responde
"¿acertaste?" sin evidencia. Aquí se mide, con las reglas duras del repo:

**Nada de look-ahead.** La entrada es el precio de la fecha de publicación de
la versión de tesis (``thesis_versions.created_at``: el instante en que ese
contenido existía) o —declarado— la primera sesión con precio disponible
dentro de ``ENTRY_PRICE_GRACE_DAYS``. La valoración es la **congelada en la
propia versión de tesis** (``expected_value`` / ``base_value``), que es
exactamente el número que el inversor leyó: recalcularla hoy con la base de
datos actual metería datos posteriores en la foto del pasado.
``assert_no_lookahead`` sigue montando la puerta sobre el precio de entrada.

**Números honestos.** Sin precio ajustado en la ventana de entrada el
horizonte sale ``N/D`` con motivo, nunca el primer precio posterior. Si la
tesis es más reciente que su horizonte, ``too_early`` y no un 0 %. Sin divisa
declarada, el retorno en la moneda base de la cartera es ``N/D``: no hay
conversión honesta. El alfa se mide cuando las dos piernas —activo e índice— son
comparables: si comparten divisa no hace falta FX, y si no, hacen falta tipos de
cambio fechados en ambos extremos. Sin benchmark, el alfa es ``N/D``, jamás
``0 = sin alfa``.

**Se delega la aritmética.** El retorno por horizonte lo calcula
``propicks_price_service.momentum_from_series`` —el único motor de retorno por
ventana del repo, con su tolerancia de ±20 días y su guardia de precio
positivo— y el max drawdown, ``tearsheet_service.compute_metrics``. Aquí no se
reimplementa ni un cociente. El ajuste por splits y dividendos vive donde tiene
que vivir: en ``MarketPrice.adj_close``, que es NULL cuando la fuente dio un
spot y nunca se rellena copiando el ``close``.

**Definición determinista del veredicto** (``OUTCOME_DEFINITIONS``, v1), sobre
el horizonte de juicio declarado:

* ``too_early`` — el horizonte de juicio aún no ha vencido. No cuenta para el
  hit-rate: acertar mañana no es acertar hoy.
* ``inconclusive`` — no hay precio de entrada, no hay precio de salida, la
  tesis no declaraba dirección, o el retorno firmado cae dentro de la banda
  muerta ``OUTCOME_DEAD_BAND``. Tampoco cuenta.
* ``thesis_right`` — el retorno firmado es ``>= +OUTCOME_DEAD_BAND``.
* ``thesis_wrong`` — el retorno firmado es ``<= -OUTCOME_DEAD_BAND``.

"Retorno firmado" es el retorno realizado por la dirección que la propia tesis
declaró (``upside_at_entry`` y, si falta, el ``rating``): +1 para una tesis que
pedía subir, -1 para una que pedía bajar. El alfa **no** entra en el veredicto
a propósito: si "acertaste" dependiera del benchmark elegido, la nota sería una
decisión, no un hecho.

**Persistencia idempotente.** Una fila por (tenant, thesis_version). Repetir no
duplica ni toca un veredicto ya cerrado: si el ``price_fingerprint`` (la entrada
y las salidas efectivamente consumidas) no cambia, no se reescribe nada. Si
cambia —porque el proveedor corrigió un cierre o porque un horizonte acaba de
medirse— se incrementa ``revision`` y la anterior queda en ``revisions`` con su
motivo. Una tesis todavía abierta (``too_early``) progresa con el calendario.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    DecisionJournalEntry,
    DecisionLesson,
    MarketPrice,
    ThesisVersion,
)
from app.models.thesis_realized_return import ThesisRealizedReturn
from app.services.number_format import format_number_es
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.propicks_price_service import momentum_from_series
from app.services.tearsheet_service import compute_metrics
from app.valuation.point_in_time import assert_no_lookahead

# Escalera de horizontes en días naturales. La tolerancia de ±20 días sobre el
# punto de salida es la del motor de retornos del repo, no una nueva.
HORIZONS: tuple[tuple[str, int], ...] = (
    ("1M", 30),
    ("3M", 90),
    ("6M", 180),
    ("1A", 365),
    ("2A", 730),
)
HORIZON_LABELS: tuple[str, ...] = tuple(label for label, _days in HORIZONS)

# Benchmark del repo: el mismo S&P 500 que usa `market_regime_quant`.
BENCHMARK_TICKER = "^GSPC"

# Sesiones siguientes a la publicación en las que se admite el precio de
# entrada, y sólo si se declara (`entry_price_status = "next_session"`).
ENTRY_PRICE_GRACE_DAYS = 5

# Banda muerta del veredicto: por debajo de ±2 % el movimiento no distingue una
# tesis acertada de una equivocada, así que se declara inconcluso en vez de
# repartir aciertos por el redondeo.
OUTCOME_DEAD_BAND = Decimal("0.02")
OUTCOME_DEFINITION_VERSION = "v1"

DEFAULT_HOLDING_HORIZON_DAYS = 180

RETURN_QUANT = Decimal("0.000001")
PRICE_QUANT = Decimal("0.000001")

OUTCOMES = ("thesis_right", "thesis_wrong", "inconclusive", "too_early")
COUNTABLE_OUTCOMES = ("thesis_right", "thesis_wrong")

HORIZON_OK = "ok"
HORIZON_TOO_EARLY = "too_early"
HORIZON_NO_ENTRY_PRICE = "no_entry_price"
HORIZON_NO_EXIT_PRICE = "no_exit_price"
HORIZON_NO_DIRECTION = "no_direction"

ENTRY_STATUS_EXACT = "exact"
ENTRY_STATUS_NEXT_SESSION = "next_session"
ENTRY_STATUS_MISSING = "missing"
ENTRY_STATUS_SPOT_ONLY = "spot_only"
ENTRY_STATUS_NO_SERIES = "no_series"
MEASURABLE_ENTRY = frozenset({ENTRY_STATUS_EXACT, ENTRY_STATUS_NEXT_SESSION})

OUTCOME_DEFINITIONS: dict[str, str] = {
    "thesis_right": (
        "El retorno firmado del horizonte de juicio es >= +2,00 %. La dirección es la "
        "que declaró la propia tesis, no la del mercado."
    ),
    "thesis_wrong": (
        "El retorno firmado del horizonte de juicio es <= -2,00 %. La dirección es la "
        "que declaró la propia tesis, no la del mercado."
    ),
    "inconclusive": (
        "No se puede juzgar: falta el precio de entrada o el de salida, la tesis no "
        "declaraba dirección, o el retorno firmado queda dentro de la banda muerta de "
        "±2,00 %. No cuenta para el hit-rate."
    ),
    "too_early": (
        "El horizonte de juicio aún no ha vencido: la tesis es más reciente que su propio "
        "horizonte. No cuenta para el hit-rate ni como error."
    ),
}

_RATING_LONG = frozenset({"buy", "overweight", "outperform", "accumulate", "add"})
_RATING_SHORT = frozenset({"sell", "underweight", "underperform", "reduce", "exit"})

_MONTHS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:meses|mes|months|month|m)(?!\w)", re.IGNORECASE)
#: Meses declarados que existen en la escalera, con sus días. Un horizonte que
#: no está en el modelo no se inventa ni se aproxima.
_DECLARED_HORIZON_DAYS: dict[int, int] = {1: 30, 3: 90, 6: 180, 12: 365, 24: 730}

N_D = "N/D"


def _dec(value: Any) -> Decimal | None:
    """Decimal o None. Acepta el string con el que un JSON vuelve el número."""
    if value is None:
        return None
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    return parsed


def _q(value: Decimal | None, quant: Decimal = RETURN_QUANT) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def _json_safe(value: Any) -> Any:
    """JSON no sabe Decimal: las columnas JSON guardan el número como texto."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _pct(value: Decimal | None) -> str:
    """Porcentaje en es-ES. ``N/D`` si no hay número."""
    if value is None:
        return N_D
    return f"{format_number_es(_q(value * 100, Decimal('0.01'))) or N_D} %"


def _signed_pct(value: Decimal | None) -> str:
    if value is None:
        return N_D
    sign = "+" if value > 0 else ""
    return f"{sign}{format_number_es(_q(value * 100, Decimal('0.01'))) or N_D} %"


def _price(value: Any) -> str:
    parsed = _dec(value)
    return N_D if parsed is None else str(_q(parsed, PRICE_QUANT))


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _label_for(days: int) -> str:
    for label, horizon_days in HORIZONS:
        if horizon_days == days:
            return label
    return f"{days}d"


class ThesisRealizedReturnService:
    """Calcula, persiste y agrega el retorno realizado de las tesis."""

    # ------------------------------------------------------------------
    # Serie de precios
    # ------------------------------------------------------------------
    @staticmethod
    def _adjusted_series(
        db: Session, company_id: int, *, until: date | None = None
    ) -> tuple[list[tuple[date, Decimal]], bool]:
        """Serie ``adj_close`` ascendente + si hay algún spot sin ajustar.

        ``adj_close`` NULL significa que la fuente dio un spot, no una serie
        ajustada por splits y dividendos: esas barras **no** pueden anclar un
        retorno realizado a lo largo de un horizonte con corporate actions
        desconocidas. Se declaran (segundo valor de retorno) en vez de
        rellenarse con el ``close``.
        """
        statement = select(MarketPrice.date, MarketPrice.adj_close).where(
            MarketPrice.company_id == company_id
        )
        if until is not None:
            statement = statement.where(MarketPrice.date <= until)
        rows = db.execute(statement.order_by(MarketPrice.date)).all()
        series = [(day, Decimal(str(px))) for day, px in rows if px is not None and px > 0]
        spot_only = any(px is None for _day, px in rows)
        return series, spot_only

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_entry(
        series: Sequence[tuple[date, Decimal]],
        spot_only: bool,
        published_at: datetime,
    ) -> dict[str, Any]:
        """Precio de entrada y la regla aplicada, siempre declarada.

        Se busca la barra de la fecha de publicación; si no existe, la primera
        sesión posterior dentro de ``ENTRY_PRICE_GRACE_DAYS`` y con
        ``entry_price_status = "next_session"``. Fuera de esa ventana: ``N/D``.
        """
        published_day = published_at.date()
        if not series:
            reason = (
                "N/D: solo hay cotizaciones spot sin serie ajustada por splits y "
                "dividendos; un retorno realizado sobre ellas no es medible."
                if spot_only
                else "N/D: no hay ninguna cotización para esta compañía."
            )
            return {
                "entry_date": None,
                "entry_price": None,
                "status": ENTRY_STATUS_SPOT_ONLY if spot_only else ENTRY_STATUS_NO_SERIES,
                "rule": reason,
                "reason": reason,
            }
        for day, price in series:
            if day == published_day:
                return {
                    "entry_date": day,
                    "entry_price": _q(price, PRICE_QUANT),
                    "status": ENTRY_STATUS_EXACT,
                    "rule": (
                        f"precio ajustado del {day.isoformat()}, la fecha de publicación "
                        "de la versión de tesis"
                    ),
                    "reason": None,
                }
        deadline = published_day + timedelta(days=ENTRY_PRICE_GRACE_DAYS)
        for day, price in series:
            # El look-ahead se cierra aquí: una fecha anterior a la publicación
            # no puede ser el precio de entrada aunque la serie la traiga.
            if day < published_day:
                continue
            if day > deadline:
                break
            return {
                "entry_date": day,
                "entry_price": _q(price, PRICE_QUANT),
                "status": ENTRY_STATUS_NEXT_SESSION,
                "rule": (
                    f"no había precio ajustado el {published_day.isoformat()}; se usa la "
                    f"primera sesión con precio dentro de los {ENTRY_PRICE_GRACE_DAYS} "
                    f"días siguientes ({day.isoformat()}), declarado"
                ),
                "reason": (
                    "precio de entrada desplazado a la sesión siguiente "
                    f"({day.isoformat()}) por falta de cotización el día de publicación"
                ),
            }
        reason = (
            f"N/D: sin precio ajustado en la fecha de publicación "
            f"({published_day.isoformat()}) ni en los {ENTRY_PRICE_GRACE_DAYS} días "
            "siguientes; no se usa el primer precio posterior."
        )
        return {
            "entry_date": None,
            "entry_price": None,
            "status": ENTRY_STATUS_MISSING,
            "rule": reason,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # Horizonte de juicio y dirección
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_holding_horizon(thesis: ThesisVersion) -> tuple[int, str]:
        """El horizonte que la tesis declara, o el 6M por defecto (declarado).

        Se lee el texto propio de la tesis (hipótesis, catalizadores, criterios
        de invalidación) y sólo se aceptan meses de la escalera estándar: un
        horizonte que no existe en el modelo no se inventa.
        """
        chunks: list[str] = [thesis.hypothesis or ""]
        for key in ("catalysts", "invalidation_criteria"):
            for item in getattr(thesis, key, None) or []:
                chunks.append(
                    " ".join(str(part) for part in item.values())
                    if isinstance(item, dict)
                    else str(item)
                )
        for chunk in chunks:
            for match in _MONTHS_RE.finditer(chunk):
                months = int(match.group(1))
                if months in _DECLARED_HORIZON_DAYS:
                    return (
                        _DECLARED_HORIZON_DAYS[months],
                        f"declarado en la tesis: {match.group(0)}",
                    )
        return DEFAULT_HOLDING_HORIZON_DAYS, "default_6m"

    @staticmethod
    def resolve_direction(thesis: ThesisVersion, upside: Decimal | None) -> tuple[int, str]:
        """+1 tesis que pedía subir, -1 que pedía bajar, 0 si no declara dirección.

        La dirección sale del ``rating``, que es la recomendación explícita: el
        signo del upside es aritmética de la valoración, no la llamada del
        analista. Una tesis ``buy`` cuyo valor razonable queda por debajo del
        precio sigue siendo una tesis larga, y llamarla corta por el signo del
        upside sería_falsear al autor. El signo del upside sólo decide cuando
        no hay rating.
        """
        rating = (thesis.rating or "").strip().lower()
        if rating in _RATING_LONG:
            return 1, f"rating {rating}"
        if rating in _RATING_SHORT:
            return -1, f"rating {rating}"
        if upside is not None:
            if upside > 0:
                return 1, "upside_at_entry positivo sin rating direccional"
            if upside < 0:
                return -1, "upside_at_entry negativo sin rating direccional"
            return 0, "upside_at_entry nulo sin rating direccional"
        return 0, f"rating {rating or 'ausente'} sin dirección declarada"

    # ------------------------------------------------------------------
    # Retorno por horizonte (motor delegado)
    # ------------------------------------------------------------------
    @staticmethod
    def _window_return(
        series: Sequence[tuple[date, Decimal]],
        entry_date: date,
        horizon_days: int,
        as_of: date,
    ) -> dict[str, Any]:
        """Retorno de la ventana delegando en el motor de retornos del repo.

        ``momentum_from_series`` recibe la serie recortada al objetivo, así que
        su propio último punto es la última barra anterior o igual al objetivo;
        su tolerancia de ±20 días y su guardia de precio positivo son las del
        repo, no unas nuevas.
        """
        target = entry_date + timedelta(days=horizon_days)
        if target > as_of:
            return {
                "status": HORIZON_TOO_EARLY,
                "target_date": target,
                "exit_date": None,
                "realized_return": None,
                "reason": (
                    f"N/D: el horizonte de {horizon_days} días termina el "
                    f"{target.isoformat()} y aún faltan {(target - as_of).days} días; "
                    "una tesis de ayer no se puntúa como un 0 %."
                ),
                "bars_used": 0,
            }
        window = [row for row in series if entry_date <= row[0] <= target]
        value = momentum_from_series(window, horizon_days)
        if value is None:
            return {
                "status": HORIZON_NO_EXIT_PRICE,
                "target_date": target,
                "exit_date": None,
                "realized_return": None,
                "reason": (
                    f"N/D: no hay serie ajustada que cubra los {horizon_days} días desde "
                    f"{entry_date.isoformat()}, o la última barra queda fuera de la "
                    f"tolerancia del objetivo {target.isoformat()}; el horizonte no se "
                    "alarga en silencio."
                ),
                "bars_used": len(window),
            }
        return {
            "status": HORIZON_OK,
            "target_date": target,
            "exit_date": window[-1][0],
            "realized_return": _q(value),
            "reason": None,
            "bars_used": len(window),
        }

    @staticmethod
    def _excursions(
        series: Sequence[tuple[date, Decimal]], entry_date: date, exit_date: date
    ) -> dict[str, Any]:
        """max_drawdown (motor del repo) y max_run_up sobre la misma wealth path."""
        window = [row for row in series if entry_date <= row[0] <= exit_date]
        if len(window) < 3:
            return {
                "max_drawdown": None,
                "max_run_up": None,
                "reason": (
                    "N/D: hacen falta al menos 3 barras ajustadas para medir la excursión "
                    f"y solo hay {len(window)}"
                ),
            }
        returns = [
            float(current[1] / previous[1] - 1)
            for previous, current in zip(window, window[1:], strict=False)
        ]
        metrics = compute_metrics(returns)
        if metrics.get("status") != "ok":
            return {
                "max_drawdown": None,
                "max_run_up": None,
                "reason": f"N/D:Excursiones no medibles ({metrics.get('status')})",
            }
        # El run-up es el gemelo del drawdown: la mayor subida desde el mínimo
        # acumulado. El repo no tiene motor de run-up, así que se calcula aquí
        # sobre la MISMA wealth path que usa `compute_metrics` (mismo inicio 1.0).
        wealth = [float(row[1] / window[0][1]) for row in window]
        running_min = wealth[0]
        max_run_up = 0.0
        for point in wealth:
            running_min = min(running_min, point)
            if running_min > 0:
                max_run_up = max(max_run_up, point / running_min - 1)
        return {
            "max_drawdown": _q(_dec(metrics["max_drawdown"])),
            "max_run_up": _q(_dec(max_run_up)),
            "reason": None,
        }

    # ------------------------------------------------------------------
    # Conversión a moneda base (FX fechado, nunca inventado)
    # ------------------------------------------------------------------
    @staticmethod
    def _to_base(
        db: Session,
        *,
        local_return: Decimal | None,
        currency: str | None,
        base_currency: str,
        entry_date: date,
        exit_date: date,
    ) -> tuple[Decimal | None, str | None]:
        if local_return is None:
            return None, "N/D: el retorno en moneda local no está medido"
        if not currency:
            return None, (
                "N/D: la compañía no declara divisa, así que el retorno no se puede "
                "expresar en la moneda base de la cartera"
            )
        if currency.upper() == base_currency.upper():
            return local_return, None
        fx = PortfolioFXService()
        entry_rate = fx.rate(
            db, quote_currency=currency, base_currency=base_currency, as_of=entry_date
        )
        exit_rate = fx.rate(
            db, quote_currency=currency, base_currency=base_currency, as_of=exit_date
        )
        if entry_rate is None or exit_rate is None:
            side = "entrada" if entry_rate is None else "salida"
            return None, (
                f"N/D: sin tipo de cambio fechado {base_currency}/{currency} en la "
                f"{side} del horizonte; no se convierte con un tipo inventado"
            )
        if entry_rate <= 0:
            return None, "N/D: tipo de cambio de entrada no positivo"
        # `rate` devuelve cuántas unidades de la divisa base vale una de la local,
        # así que el retorno en moneda base es el local por el appreciated del FX.
        converted = (1 + float(local_return)) * float(exit_rate) / float(entry_rate)
        return _q(_dec(converted - 1)), None

    # ------------------------------------------------------------------
    # Un horizonte
    # ------------------------------------------------------------------
    def _horizon(
        self,
        db: Session,
        *,
        series: Sequence[tuple[date, Decimal]],
        benchmark: Sequence[tuple[date, Decimal]],
        benchmark_currency: str | None,
        benchmark_status: str,
        entry_date: date | None,
        entry_status: str,
        horizon_label: str,
        horizon_days: int,
        as_of: date,
        currency: str | None,
        base_currency: str,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "horizon": horizon_label,
            "horizon_days": horizon_days,
            "status": HORIZON_NO_ENTRY_PRICE,
            "target_date": None,
            "exit_date": None,
            "exit_price": None,
            "realized_return": None,
            "realized_return_base": None,
            "benchmark_return": None,
            "alpha": None,
            "max_drawdown": None,
            "max_run_up": None,
            "reason": None,
            "base_reason": None,
            "benchmark_reason": None,
            "alpha_reason": None,
            "excursion_reason": None,
            "bars_used": 0,
        }
        if entry_date is None:
            item["target_date"] = None
            item["reason"] = (
                f"N/D: el precio de entrada no está disponible ({entry_status}); sin él el "
                f"horizonte de {horizon_days} días no se puede medir."
            )
            return item

        computed = self._window_return(series, entry_date, horizon_days, as_of)
        item["target_date"] = _iso(computed["target_date"])
        item["status"] = computed["status"]
        item["exit_date"] = _iso(computed["exit_date"])
        item["realized_return"] = computed["realized_return"]
        item["reason"] = computed["reason"]
        item["bars_used"] = computed["bars_used"]
        exit_date = computed["exit_date"]
        if exit_date is not None:
            exit_price = next(row[1] for row in series if row[0] == exit_date)
            item["exit_price"] = _q(exit_price, PRICE_QUANT)
        if computed["status"] != HORIZON_OK or exit_date is None:
            return item

        local_return = _dec(computed["realized_return"])
        asset_base, asset_reason = self._to_base(
            db,
            local_return=local_return,
            currency=currency,
            base_currency=base_currency,
            entry_date=entry_date,
            exit_date=exit_date,
        )
        item["realized_return_base"] = asset_base
        item["base_reason"] = asset_reason

        bench = self._window_return(benchmark, entry_date, horizon_days, as_of)
        bench_local = _dec(bench["realized_return"])
        if benchmark_status != "ok":
            bench_reason = (
                f"N/D: sin benchmark utilizable ({benchmark_status}); el alfa no se inventa como 0"
            )
            item["benchmark_return"] = None
            item["benchmark_reason"] = bench_reason
        elif bench_local is None:
            item["benchmark_return"] = None
            item["benchmark_reason"] = bench["reason"]
        elif benchmark_currency and currency and benchmark_currency == currency:
            # Misma divisa en las dos piernas: el tipo de cambio se cancela y el
            # alfa es medible sin FX. Convertirlo a la moneda base de la cartera
            # solo servia para perder la cifra.
            item["benchmark_return"] = bench_local
            item["benchmark_reason"] = None
        else:
            bench_base, bench_reason = self._to_base(
                db,
                local_return=bench_local,
                currency=benchmark_currency,
                base_currency=base_currency,
                entry_date=entry_date,
                exit_date=exit_date,
            )
            item["benchmark_return"] = bench_base
            item["benchmark_reason"] = bench_reason
            bench_local = bench_base

        alpha, alpha_reason = self._alpha(
            asset_local=local_return,
            asset_base=asset_base,
            benchmark=bench_local,
            asset_reason=asset_reason,
            benchmark_reason=item["benchmark_reason"],
            currency=currency,
            benchmark_currency=benchmark_currency,
        )
        item["alpha"] = alpha
        item["alpha_reason"] = alpha_reason

        excursions = self._excursions(series, entry_date, exit_date)
        item["max_drawdown"] = excursions["max_drawdown"]
        item["max_run_up"] = excursions["max_run_up"]
        item["excursion_reason"] = excursions["reason"]
        return item

    @staticmethod
    def _alpha(
        *,
        asset_local: Decimal | None,
        asset_base: Decimal | None,
        benchmark: Decimal | None,
        asset_reason: str | None,
        benchmark_reason: str | None,
        currency: str | None,
        benchmark_currency: str | None,
    ) -> tuple[Decimal | None, str | None]:
        """Alfa = retorno del activo - retorno del benchmark, en la misma base.

        Si las dos piernas cotizan en la misma divisa ya son comparables y el
        alfa se mide sin tocar el FX: convertir un activo y un índice en USD a
        la moneda base de la cartera sólo servía para perder la cifra. Si las
        divisas difieren hace falta convertir las dos con tipos fechados. Sin
        ninguna de las dos cosas el alfa es ``N/D``, nunca ``0 = sin alfa``.
        """
        if benchmark is None:
            return None, benchmark_reason or "N/D: benchmark sin retorno medible"
        if asset_local is not None and currency and currency == benchmark_currency:
            return _q(asset_local - benchmark), None
        if asset_base is None:
            return None, asset_reason
        return _q(asset_base - benchmark), None

    # ------------------------------------------------------------------
    # Veredicto
    # ------------------------------------------------------------------
    @classmethod
    def _classify(
        cls,
        *,
        entry_status: str,
        entry_reason: str | None,
        direction: int,
        direction_source: str,
        judgement: dict[str, Any] | None,
        holding_days: int,
    ) -> tuple[str, str, str]:
        if entry_status not in MEASURABLE_ENTRY:
            return (
                "inconclusive",
                entry_reason or "N/D: sin precio de entrada no hay veredicto",
                HORIZON_NO_ENTRY_PRICE,
            )
        if judgement is None:
            return (
                "inconclusive",
                f"N/D: el horizonte de juicio de {holding_days} días no está en la escalera",
                HORIZON_NO_EXIT_PRICE,
            )
        if judgement["status"] == HORIZON_TOO_EARLY:
            return (
                "too_early",
                judgement["reason"]
                or f"N/D: el horizonte de {holding_days} días aún no ha vencido",
                HORIZON_TOO_EARLY,
            )
        if judgement["status"] != HORIZON_OK:
            return (
                "inconclusive",
                judgement["reason"]
                or f"N/D: el horizonte de {holding_days} días no tiene precio de salida",
                judgement["status"],
            )
        if direction == 0:
            return (
                "inconclusive",
                "Inconcluso: la tesis no declara dirección "
                f"({direction_source}); sin ella el retorno de {holding_days} días no se "
                "puede calificar de acierto ni de error.",
                HORIZON_NO_DIRECTION,
            )
        realized = _dec(judgement.get("realized_return"))
        signed = realized * direction if realized is not None else None
        alpha = _dec(judgement.get("alpha"))
        common = (
            f"Retorno firmado {_signed_pct(signed)} a {holding_days} días "
            f"(retorno {_signed_pct(realized)}, alfa "
            f"{_signed_pct(alpha) if alpha is not None else N_D}), dirección "
            f"{direction:+d} por {direction_source}."
        )
        band = format_number_es(OUTCOME_DEAD_BAND * 100)
        if signed is None:
            return "inconclusive", f"N/D: retorno no medible. {common}", HORIZON_OK
        if signed >= OUTCOME_DEAD_BAND:
            return "thesis_right", f"Tesis acertada: {common}", HORIZON_OK
        if signed <= -OUTCOME_DEAD_BAND:
            return "thesis_wrong", f"Tesis fallada: {common}", HORIZON_OK
        return (
            "inconclusive",
            f"Inconcluso: {common} El retorno firmado queda dentro de la banda muerta "
            f"de ±{band} %.",
            HORIZON_OK,
        )

    # ------------------------------------------------------------------
    # Cálculo completo
    # ------------------------------------------------------------------
    @staticmethod
    def _fair_value(thesis: ThesisVersion) -> tuple[Decimal | None, str]:
        """La valoración congelada en la versión, tal como la leyó el inversor."""
        for value, source in (
            (thesis.expected_value, "thesis_expected_value"),
            (thesis.base_value, "thesis_base_value"),
            (thesis.bull_value, "thesis_bull_value"),
            (thesis.bear_value, "thesis_bear_value"),
        ):
            parsed = _dec(value)
            if parsed is not None and parsed > 0:
                return parsed, source
        return None, "absent"

    @staticmethod
    def _benchmark(db: Session) -> tuple[list[tuple[date, Decimal]], str, str | None]:
        company = db.scalar(select(Company).where(Company.ticker == BENCHMARK_TICKER))
        currency = (company.currency or "").strip().upper() or None if company else None
        if company is None:
            return [], "missing_company", None
        series, _spot = ThesisRealizedReturnService._adjusted_series(db, company.id)
        if not series:
            return [], "no_adjusted_prices", currency
        return series, "ok", currency

    @staticmethod
    def _decision_lesson(
        db: Session, company: Company, thesis: ThesisVersion
    ) -> tuple[int | None, str]:
        """Enlaza la lección derivada, sólo en lectura, si existe.

        Orden determinista: primero la lección colgada de la decisión que
        llevaba ESTA versión de tesis; si no hay decisión, la lección más
        reciente de la compañía. Nunca se crea ni se modifica una lección.
        """
        decision_ids = list(
            db.scalars(
                select(DecisionJournalEntry.id).where(
                    DecisionJournalEntry.thesis_version_id == thesis.id
                )
            ).all()
        )
        if decision_ids:
            lesson_id = db.scalar(
                select(DecisionLesson.id)
                .where(DecisionLesson.decision_journal_entry_id.in_(decision_ids))
                .order_by(desc(DecisionLesson.id))
                .limit(1)
            )
            if lesson_id is not None:
                return lesson_id, "decision_journal_entry"
        lesson_id = db.scalar(
            select(DecisionLesson.id)
            .where(DecisionLesson.company_id == company.id)
            .order_by(desc(DecisionLesson.id))
            .limit(1)
        )
        if lesson_id is not None:
            return lesson_id, "company_latest"
        return None, "none"

    def compute(
        self,
        db: Session,
        company: Company,
        thesis: ThesisVersion,
        *,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """El payload completo de la foto tesis ↔ mercado. Sin efectos de orden."""
        as_of = as_of or date.today()
        published_at = _aware(thesis.created_at)
        published_day = published_at.date()

        series, spot_only = self._adjusted_series(db, company.id)
        entry = self.resolve_entry(series, spot_only, published_at)
        entry_date = entry["entry_date"]
        entry_price = _dec(entry["entry_price"])
        if entry_date is not None:
            # La puerta del repo, orientada al look-ahead que importa aquí: la
            # publicación no puede ser POSTERIOR al precio de entrada. Usarla al
            # revés (as_of=publicación) rechazaría la sesión siguiente, que la
            # regla admite y declara explícitamente.
            assert_no_lookahead(
                as_of=entry_date, data_date=published_day, label="publicación de la tesis"
            )

        currency = (company.currency or "").strip().upper() or None
        fair_value, fair_value_source = self._fair_value(thesis)
        upside: Decimal | None = None
        if fair_value is not None and entry_price is not None and entry_price > 0:
            upside = _q(fair_value / entry_price - 1)
        holding_days, holding_source = self.resolve_holding_horizon(thesis)
        direction, direction_source = self.resolve_direction(thesis, upside)

        base_currency = PortfolioFXService().base_currency(db)
        benchmark, benchmark_status, benchmark_currency = self._benchmark(db)

        horizons: list[dict[str, Any]] = []
        fingerprint: list[str] = [f"{company.ticker}|{thesis.id}|{published_day}"]
        for label, days in HORIZONS:
            item = self._horizon(
                db,
                series=series,
                benchmark=benchmark,
                benchmark_currency=benchmark_currency,
                benchmark_status=benchmark_status,
                entry_date=entry_date,
                entry_status=entry["status"],
                horizon_label=label,
                horizon_days=days,
                as_of=as_of,
                currency=currency,
                base_currency=base_currency,
            )
            horizons.append(item)
            if item["status"] == HORIZON_OK:
                assert_no_lookahead(
                    as_of=as_of,
                    data_date=date.fromisoformat(str(item["exit_date"])),
                    label=f"precio de salida {label}",
                )
                fingerprint.append(
                    f"{label}:{item['exit_date']}:{item['exit_price']}:"
                    f"{item['realized_return']}"
                )
            else:
                fingerprint.append(f"{label}:{item['status']}")
        if entry_date is not None and entry_price is not None:
            fingerprint.insert(1, f"entry:{entry_date}:{entry_price}")

        judgement = next((h for h in horizons if h["horizon_days"] == holding_days), None)
        outcome, verdict_reason, judgement_status = self._classify(
            entry_status=entry["status"],
            entry_reason=entry["reason"],
            direction=direction,
            direction_source=direction_source,
            judgement=judgement,
            holding_days=holding_days,
        )
        lesson_id, lesson_link = self._decision_lesson(db, company, thesis)

        return {
            "company_id": company.id,
            "ticker": company.ticker,
            "thesis_version_id": thesis.id,
            "thesis_version": thesis.version,
            "thesis_published_at": published_at,
            "thesis_status": thesis.status,
            "currency": currency,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "entry_price_status": entry["status"],
            "entry_price_rule": entry["rule"],
            "fair_value_at_entry": fair_value,
            "fair_value_source": fair_value_source,
            "upside_at_entry": upside,
            "holding_horizon_days": holding_days,
            "holding_horizon_source": holding_source,
            "judgement_horizon": _label_for(holding_days),
            "judgement_status": judgement_status,
            "horizons": horizons,
            "outcome": outcome,
            "outcome_definition_version": OUTCOME_DEFINITION_VERSION,
            "verdict_reason": verdict_reason,
            "counts_toward_hit_rate": outcome in COUNTABLE_OUTCOMES,
            "benchmark_ticker": BENCHMARK_TICKER if benchmark else None,
            "benchmark_status": benchmark_status,
            "base_currency": base_currency,
            "decision_lesson_id": lesson_id,
            "decision_lesson_link": lesson_link,
            "metadata_": {
                "as_of": as_of.isoformat(),
                "benchmark_bars": len(benchmark),
                "spot_only_prices": spot_only,
                "entry_price_rule": entry["rule"],
                "entry_price_reason": entry["reason"],
                "direction": direction,
                "direction_source": direction_source,
                "dead_band": str(OUTCOME_DEAD_BAND),
                "entry_price_grace_days": ENTRY_PRICE_GRACE_DAYS,
                "holding_horizon_source": holding_source,
                "outcome_definitions": OUTCOME_DEFINITIONS,
                "return_engine": "propicks_price_service.momentum_from_series (adj_close)",
                "drawdown_engine": "tearsheet_service.compute_metrics",
            },
            "price_fingerprint": hashlib.sha256("|".join(fingerprint).encode()).hexdigest(),
        }

    # ------------------------------------------------------------------
    # Persistencia idempotente
    # ------------------------------------------------------------------
    _COLUMN_KEYS = (
        "company_id",
        "ticker",
        "thesis_version_id",
        "thesis_version",
        "thesis_published_at",
        "thesis_status",
        "currency",
        "entry_date",
        "entry_price",
        "entry_price_status",
        "entry_price_rule",
        "fair_value_at_entry",
        "fair_value_source",
        "upside_at_entry",
        "holding_horizon_days",
        "holding_horizon_source",
        "judgement_horizon",
        "judgement_status",
        "outcome",
        "outcome_definition_version",
        "verdict_reason",
        "counts_toward_hit_rate",
        "benchmark_ticker",
        "benchmark_status",
        "base_currency",
        "decision_lesson_id",
        "decision_lesson_link",
    )

    _MATERIAL_KEYS = (
        "entry_date",
        "entry_price",
        "entry_price_status",
        "fair_value_at_entry",
        "upside_at_entry",
        "holding_horizon_days",
        "horizons",
        "outcome",
        "verdict_reason",
        "decision_lesson_id",
        "benchmark_status",
    )

    @classmethod
    def _columns(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Columnas escalares del payload; los horizontos van serializados."""
        columns = {key: payload[key] for key in cls._COLUMN_KEYS}
        columns["horizons"] = _json_safe(payload["horizons"])
        columns["metadata_"] = _json_safe(payload["metadata_"])
        return columns

    @classmethod
    def _columns_from_row(cls, row: ThesisRealizedReturn) -> dict[str, Any]:
        """Las mismas columnas leídas de la fila, para comparar sin adivinar."""
        columns: dict[str, Any] = {key: getattr(row, key) for key in cls._COLUMN_KEYS}
        columns["horizons"] = row.horizons or []
        columns["metadata_"] = row.metadata_ or {}
        return columns

    @classmethod
    def _material(cls, columns: dict[str, Any]) -> str:
        """Lo que, si cambia, cambia el resultado. `computed_at` no cuenta."""
        return "|".join(str(columns.get(key)) for key in cls._MATERIAL_KEYS)

    @classmethod
    def _apply(cls, row: ThesisRealizedReturn, columns: dict[str, Any]) -> None:
        for key, value in columns.items():
            setattr(row, key, value)

    def persist(
        self,
        db: Session,
        company: Company,
        thesis: ThesisVersion,
        *,
        as_of: date | None = None,
    ) -> tuple[ThesisRealizedReturn, bool]:
        """(registro, cambió). Repetir no duplica ni reescribe un cierre."""
        payload = self.compute(db, company, thesis, as_of=as_of)
        columns = self._columns(payload)
        now = datetime.now(UTC)
        existing = db.scalar(
            select(ThesisRealizedReturn).where(
                ThesisRealizedReturn.thesis_version_id == thesis.id
            )
        )
        if existing is None:
            row = ThesisRealizedReturn(**columns)
            row.price_fingerprint = payload["price_fingerprint"]
            row.revisions = [
                {
                    "revision": 1,
                    "price_fingerprint": payload["price_fingerprint"],
                    "outcome": payload["outcome"],
                    "computed_at": now.isoformat(),
                    "motivo": "alta",
                }
            ]
            row.computed_at = now
            db.add(row)
            db.commit()
            db.refresh(row)
            return row, True

        if existing.price_fingerprint != payload["price_fingerprint"]:
            closed_now = payload["judgement_status"] == HORIZON_OK
            motivo = (
                "el horizonte de juicio se cerró"
                if closed_now and existing.judgement_status != HORIZON_OK
                else "los precios consumidos o el estado de los horizontes cambiaron"
            )
            history = list(existing.revisions or [])
            history.append(
                {
                    "revision": existing.revision,
                    "price_fingerprint": existing.price_fingerprint,
                    "outcome": existing.outcome,
                    "computed_at": existing.computed_at.isoformat()
                    if existing.computed_at
                    else None,
                    "motivo": motivo,
                    "superseded_by_price_fingerprint": payload["price_fingerprint"],
                }
            )
            existing.revisions = history
            existing.revision = (existing.revision or 1) + 1
            self._apply(existing, columns)
            existing.price_fingerprint = payload["price_fingerprint"]
            existing.computed_at = now
            db.commit()
            db.refresh(existing)
            return existing, True

        if existing.judgement_status == HORIZON_OK:
            # Veredicto cerrado y precios idénticos: no se toca lo ya dicho.
            return existing, False

        if self._material(columns) != self._material(self._columns_from_row(existing)):
            self._apply(existing, columns)
            existing.price_fingerprint = payload["price_fingerprint"]
            existing.computed_at = now
            db.commit()
            db.refresh(existing)
            return existing, True
        return existing, False

    # ------------------------------------------------------------------
    # Entradas públicas
    # ------------------------------------------------------------------
    def recompute_for_company(
        self, db: Session, company: Company
    ) -> list[ThesisRealizedReturn]:
        theses = list(
            db.scalars(
                select(ThesisVersion)
                .where(ThesisVersion.company_id == company.id)
                .order_by(ThesisVersion.version)
            ).all()
        )
        return [self.persist(db, company, thesis)[0] for thesis in theses]

    def recompute_portfolio(self, db: Session, *, limit: int = 200) -> dict[str, Any]:
        """Recalcula las tesis del tenant. Trabajo acotado y declarado.

        No es un job: por tesis son un puñado de consultas sobre precios ya
        persistidos (sin red, sin LLM), así que un límite explícito mantiene el
        request acotado y la respuesta declara si se truncó.
        """
        theses = list(
            db.scalars(select(ThesisVersion).order_by(ThesisVersion.id).limit(limit + 1)).all()
        )
        truncated = len(theses) > limit
        theses = theses[:limit]
        updated = 0
        for thesis in theses:
            company = db.get(Company, thesis.company_id)
            if company is None:
                continue
            updated += int(self.persist(db, company, thesis)[1])
        return {
            "recomputados": len(theses),
            "actualizados": updated,
            "sin_cambios": len(theses) - updated,
            "limite": limit,
            "truncado": truncated,
        }

    def for_company(self, db: Session, company_id: int) -> list[ThesisRealizedReturn]:
        return list(
            db.scalars(
                select(ThesisRealizedReturn)
                .where(ThesisRealizedReturn.company_id == company_id)
                .order_by(desc(ThesisRealizedReturn.thesis_version))
            ).all()
        )

    def for_thesis(self, db: Session, thesis_id: int) -> ThesisRealizedReturn | None:
        return db.scalar(
            select(ThesisRealizedReturn).where(
                ThesisRealizedReturn.thesis_version_id == thesis_id
            )
        )

    @staticmethod
    def _stats(values: list[Decimal]) -> dict[str, Any]:
        if not values:
            return {"n": 0, "media": None, "mediana": None, "desviacion": None}
        ordered = sorted(values)
        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )
        mean = sum(values, Decimal("0")) / len(values)
        variance = sum(((v - mean) ** 2 for v in values), Decimal("0")) / len(values)
        return {
            "n": len(values),
            "media": _q(mean),
            "mediana": _q(median),
            "desviacion": _q(variance.sqrt()),
        }

    def portfolio_summary(self, db: Session) -> dict[str, Any]:
        """Hit-rate CON denominador y con los excluidos a la vista."""
        rows = list(
            db.scalars(select(ThesisRealizedReturn).order_by(ThesisRealizedReturn.id)).all()
        )
        counts: dict[str, int] = dict.fromkeys(OUTCOMES, 0)
        for row in rows:
            counts[row.outcome] = counts.get(row.outcome, 0) + 1
        right = counts["thesis_right"]
        denominator = right + counts["thesis_wrong"]
        hit_rate = _dec(str(round(right / denominator, 4))) if denominator else None

        realized: dict[str, list[Decimal]] = {label: [] for label in HORIZON_LABELS}
        alpha: dict[str, list[Decimal]] = {label: [] for label in HORIZON_LABELS}
        sin_alfa = 0
        for row in rows:
            for item in row.horizons or []:
                label = item.get("horizon")
                if label not in realized:
                    continue
                value = _dec(item.get("realized_return"))
                if value is not None:
                    realized[label].append(value)
                alpha_value = _dec(item.get("alpha"))
                if alpha_value is None:
                    sin_alfa += 1
                else:
                    alpha[label].append(alpha_value)

        return {
            "as_of": date.today().isoformat(),
            "casos_totales": len(rows),
            "denominador_hit_rate": denominator,
            "hit_rate": hit_rate,
            "hit_rate_texto": (
                f"{right} aciertos sobre {denominator} tesis juzgadas "
                f"({_pct(hit_rate)})" if denominator else N_D
            ),
            "hit_rate_sin_datos": denominator == 0,
            "conteo": counts,
            "excluidos_del_hit_rate": {
                "inconclusive": counts["inconclusive"],
                "too_early": counts["too_early"],
                "motivo": (
                    "una tesis sin precio de entrada, dentro de la banda muerta o más "
                    "reciente que su horizonte no es ni acierto ni fallo: contarla como "
                    "fallo baja el acierto, ignorarla infla el resultado"
                ),
            },
            "retorno_realizado_por_horizonte": {
                label: self._stats(realized[label]) for label in HORIZON_LABELS
            },
            "alfa_por_horizonte": {label: self._stats(alpha[label]) for label in HORIZON_LABELS},
            "horizontes_sin_alfa": sin_alfa,
            "sin_alfa_motivo": (
                "N/D: sin benchmark, sin serie ajustada del índice o sin tipo de cambio "
                "fechado. Un alfa ausente no es un alfa de cero."
            ),
            "benchmark": BENCHMARK_TICKER,
            "outcome_definitions": OUTCOME_DEFINITIONS,
        }


def realized_return_payload(row: ThesisRealizedReturn) -> dict[str, Any]:
    """Serializa un registro para la API, en español y con N/D + motivo."""
    return {
        "ticker": row.ticker,
        "thesis_id": row.thesis_version_id,
        "thesis_version": row.thesis_version,
        "tesis_publicada": _iso(row.thesis_published_at) or N_D,
        "estado_tesis": row.thesis_status,
        "divisa": row.currency or N_D,
        "entrada": {
            "fecha": _iso(row.entry_date) or N_D,
            "precio": _price(row.entry_price),
            "estado": row.entry_price_status,
            "regla": row.entry_price_rule,
        },
        "valoracion_en_entrada": {
            "fair_value": _price(row.fair_value_at_entry),
            "origen": row.fair_value_source,
            "upside": _pct(row.upside_at_entry),
        },
        "horizonte_de_juicio": {
            "etiqueta": row.judgement_horizon,
            "dias": row.holding_horizon_days,
            "origen": row.holding_horizon_source,
            "estado": row.judgement_status,
        },
        "horizontes": [_horizon_payload(item) for item in (row.horizons or [])],
        "veredicto": {
            "outcome": row.outcome,
            "definicion": OUTCOME_DEFINITIONS.get(row.outcome, ""),
            "motivo": row.verdict_reason or N_D,
            "cuenta_en_hit_rate": row.counts_toward_hit_rate,
            "version_definicion": row.outcome_definition_version,
        },
        "benchmark": {
            "ticker": row.benchmark_ticker or N_D,
            "estado": row.benchmark_status,
        },
        "moneda_base": row.base_currency,
        "leccion": _lesson_payload(row),
        "revision": row.revision,
        "price_fingerprint": row.price_fingerprint,
        "revisiones": row.revisions or [],
        "calculado_en": _iso(row.computed_at) or N_D,
    }


def _lesson_payload(row: ThesisRealizedReturn) -> dict[str, Any]:
    if row.decision_lesson_id is None:
        return {
            "decision_lesson_id": N_D,
            "enlace": row.decision_lesson_link,
            "motivo": "N/D: no hay ninguna DecisionLesson derivable para esta tesis",
        }
    return {
        "decision_lesson_id": row.decision_lesson_id,
        "enlace": row.decision_lesson_link,
        "motivo": None,
    }


def _nd(value: Decimal | None, reason: str | None = None) -> dict[str, Any]:
    """Toda cifra sale con su motivo: un N/D sin motivo es una cifra que miente."""
    if value is None:
        return {"valor": N_D, "motivo": reason or "N/D: no medible con los datos actuales"}
    return {"valor": _pct(value), "motivo": None}


def _horizon_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "horizonte": item.get("horizon"),
        "dias": item.get("horizon_days"),
        "estado": item.get("status"),
        "medible": item.get("status") == HORIZON_OK,
        "fecha_objetivo": item.get("target_date") or N_D,
        "salida": {
            "fecha": item.get("exit_date") or N_D,
            "precio": _price(item.get("exit_price")),
        },
        "retorno_realizado": _nd(
            _dec(item.get("realized_return")),
            item.get("reason") or item.get("base_reason"),
        ),
        "retorno_realizado_base": _nd(
            _dec(item.get("realized_return_base")),
            item.get("base_reason") or item.get("reason"),
        ),
        "retorno_benchmark": _nd(
            _dec(item.get("benchmark_return")),
            item.get("benchmark_reason") or item.get("reason"),
        ),
        "alfa": _nd(_dec(item.get("alpha")), item.get("alpha_reason")),
        "max_drawdown": _nd(
            _dec(item.get("max_drawdown")), item.get("excursion_reason")
        ),
        "max_run_up": _nd(_dec(item.get("max_run_up")), item.get("excursion_reason")),
        "barras_usadas": item.get("bars_used"),
    }


__all__ = [
    "BENCHMARK_TICKER",
    "COUNTABLE_OUTCOMES",
    "HORIZONS",
    "OUTCOMES",
    "OUTCOME_DEAD_BAND",
    "OUTCOME_DEFINITIONS",
    "ThesisRealizedReturnService",
    "realized_return_payload",
]
