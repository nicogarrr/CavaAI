"""Point-in-time guard against look-ahead bias.

Any valuation/backtest computed "as of" a date must only observe data that
existed on or before that date. Observing later data (future prices,
not-yet-published fundamentals) silently inflates backtest returns and
invalidates the analysis. These helpers fail loudly instead.

Precision matters as much as the cutoff: un periodo persistido como
``"2025-09-30:FY"`` (lo que escribe la ingesta SEC/ESEF) DECLARA su fecha de
cierre, y un ano a secas no dice nada sobre los meses. Contrastar contra el ano
dejaba pasar un cierre meses en el futuro siempre que coincidiera con el ano del
cutoff, asi que aqui el periodo se compara contra su fecha cuando la trae.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime


class LookaheadError(ValueError):
    """A calculation observed data dated after its ``as_of`` cutoff."""


def assert_no_lookahead(
    *, as_of: date, data_date: date | None, label: str = "data"
) -> None:
    """Raise :class:`LookaheadError` if ``data_date`` is after ``as_of``.

    ``data_date=None`` (unknown date) passes: the guard only rejects data
    *known* to be from the future, never blocks on missing metadata.
    """
    if data_date is not None and data_date > as_of:
        raise LookaheadError(
            f"{label} dated {data_date.isoformat()} is after as_of "
            f"{as_of.isoformat()}; using it would introduce look-ahead bias"
        )


def assert_fiscal_year_no_lookahead(
    *, as_of: date, fiscal_year: int | None, label: str = "data"
) -> None:
    """Year-granularity variant for fundamentals carrying only a fiscal year."""
    if fiscal_year is not None and fiscal_year > as_of.year:
        raise LookaheadError(
            f"{label} from fiscal year {fiscal_year} is after as_of "
            f"{as_of.isoformat()}; using it would introduce look-ahead bias"
        )


PRECISION_EXACT_DATE = "exact_date"
PRECISION_FISCAL_YEAR = "fiscal_year"
PRECISION_UNKNOWN = "unknown"

# "2025-09-30" embebido en "2025-09-30:FY" / "2025-09-30:10-K". El par de
# lookarounds exige digitos/no-digitos a ambos lados para que un ISIN
# ("US0378331005") o un CIK ("CIK0000320193") no se lean como un ano.
_ISO_DATE_IN_TEXT = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_YEAR_IN_TEXT = re.compile(r"(?<!\d)(\d{4})(?!\d)")


@dataclass(frozen=True)
class PeriodBounds:
    """Lo que un periodo persistido permite afirmar sobre su temporalidad.

    ``end_date`` es la fecha de CIERRE cuando el periodo la declara; es la
    unica magnitud que descarta look-ahead DENTRO de un mismo ejercicio.
    ``fiscal_year`` se puebla solo si no hay fecha, porque un ano no acota meses.
    """

    raw: str | None = None
    end_date: date | None = None
    fiscal_year: int | None = None

    @property
    def precision(self) -> str:
        if self.end_date is not None:
            return PRECISION_EXACT_DATE
        if self.fiscal_year is not None:
            return PRECISION_FISCAL_YEAR
        return PRECISION_UNKNOWN


def _coerce_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def parse_period_bounds(period: object) -> PeriodBounds:
    """Interpreta los formatos de periodo que el sistema persiste de verdad.

    Cubre el dominante ``"<fin>:FY"`` de la ingesta SEC/ESEF y sus variantes de
    etiqueta (``"<fin>:Q3"``, ``"<fin>:ANNUAL"``, ``"<fin>:10-K"``), la forma
    legada (``"FY2025"``, ``"2025"``, ``"FY"``, ``"ANNUAL"``), los rangos de
    metricas calculadas (``"FY2020-FY2025"``), una ISO suelta y objetos
    ``date``/``datetime``.

    Ante varios candidatos se queda con el MAXIMO de cada magnitud: en un rango
    el extremo mas reciente es el que acota el riesgo. Tomar el primero hacia
    "FY2020-FY2025" con cutoff 2021 y validaba un dato de 2025.

    Lo que no encaja en ninguno de esos formatos se devuelve sin fecha ni ano
    (``precision == "unknown"``): el guard lo ignora, pero quien lo llame puede
    registrarlo como opaco en vez de perderlo en silencio.
    """
    if period is None:
        return PeriodBounds(raw=None)
    if isinstance(period, (date, datetime)):
        return PeriodBounds(raw=str(period), end_date=_coerce_date(period))
    if not isinstance(period, str):
        return PeriodBounds(raw=str(period))
    text = period.strip()
    if not text:
        return PeriodBounds(raw=text)

    exact = _coerce_date(text)
    if exact is not None:
        return PeriodBounds(raw=text, end_date=exact)

    ends: list[date] = []
    for year, month, day in _ISO_DATE_IN_TEXT.findall(text):
        try:
            ends.append(date(int(year), int(month), int(day)))
        except ValueError:  # "2025-13-45": no es fecha, y tampoco es un ano
            continue
    if ends:
        return PeriodBounds(raw=text, end_date=max(ends))

    years = [int(year) for year in _YEAR_IN_TEXT.findall(text)]
    return PeriodBounds(raw=text, fiscal_year=max(years) if years else None)


def assert_period_no_lookahead(
    *, as_of: date, period: object, label: str = "data"
) -> PeriodBounds:
    """Guard de un periodo persistido, en la precision que el propio declare.

    Delega en :func:`assert_no_lookahead` /
    :func:`assert_fiscal_year_no_lookahead` para que el contrato publico siga
    siendo el unico sitio donde se decide que es futuro. Devuelve los limites
    interpretados para que el llamante pueda auditar con que precision se
    comprobo cada periodo.
    """
    bounds = parse_period_bounds(period)
    detail = label if bounds.raw is None else f"{label} {bounds.raw}"
    if bounds.end_date is not None:
        assert_no_lookahead(as_of=as_of, data_date=bounds.end_date, label=detail)
    else:
        assert_fiscal_year_no_lookahead(
            as_of=as_of, fiscal_year=bounds.fiscal_year, label=detail
        )
    return bounds


AS_OF_SOURCE_EXPLICIT = "explicit"
AS_OF_SOURCE_VALUATION = "valuation"
AS_OF_SOURCE_TRACE = "trace"
AS_OF_SOURCE_TODAY = "today_default"


@dataclass(frozen=True)
class AsOfResolution:
    """Cutoff del guard mas la procedencia que lo produjo."""

    cutoff: date
    source: str

    @property
    def inferred(self) -> bool:
        """True cuando el cutoff se infirio en vez de venir pedido."""
        return self.source == AS_OF_SOURCE_TODAY


def _mapping_get(mapping: object, key: str) -> object:
    return mapping.get(key) if isinstance(mapping, Mapping) else None


def resolve_as_of(
    *,
    as_of: object = None,
    valuation: Mapping[str, object] | None = None,
    trace: Mapping[str, object] | None = None,
    today: date | None = None,
) -> AsOfResolution:
    """Resuelve el cutoff del guard y declara de donde salio.

    Precedencia: parametro explicito -> ``valuation["as_of"]`` ->
    ``trace["as_of"]`` -> hoy.

    El ultimo paso es un default DELIBERADO, no un silencio. Los llamantes que
    no pasan ``as_of`` valoran la empresa HOY (ruta GET de valoracion, earnings,
    red team, thesis), y para ellos "hoy" es su as_of real; exigirlo
    obligaria a cambiar cuatro ficheros de produccion que no son de este modulo.
    Lo inaceptable era que el cutoff quedara invisible, asi que se devuelve
    marcado como ``inferred`` y el trace lo graba: una valoracion sin ``as_of``
    queda auditada como tal en vez de aparentar un anclaje que nadie pidio.

    Un ``as_of`` explicito pero mal formado si es error: ahi el silencio seria
    un fallo, porque el llamante si quiere una fecha y le llega otra cosa.
    """
    for value, source in (
        (as_of, AS_OF_SOURCE_EXPLICIT),
        (_mapping_get(valuation, "as_of"), AS_OF_SOURCE_VALUATION),
        (_mapping_get(trace, "as_of"), AS_OF_SOURCE_TRACE),
    ):
        if value is not None:
            parsed = _coerce_date(value)
            if parsed is None:
                raise ValueError(f"Valuation as_of must be an ISO date, got {value!r}")
            return AsOfResolution(cutoff=parsed, source=source)
    return AsOfResolution(cutoff=today or date.today(), source=AS_OF_SOURCE_TODAY)
