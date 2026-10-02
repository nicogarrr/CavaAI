"""Point-in-time knowledge bounds for a single observation.

``app.valuation.point_in_time`` answers one question: is this date after my
cutoff? A backtest needs two more answers before it may trust an input:

1. *When did the period end?* ``FinancialFact.period`` is free text ("FY2025",
   "2025-12-31", "Q3 2025", ...), so the period end has to be resolved with an
   explicit precision instead of guessed.
2. *When did the world learn about it?* A FY2024 fact filed in 2026 was not
   knowable in 2025 even though its period is in the past. The publication date
   of the source document is a second, independent axis.

A fact is only usable in a replay when BOTH axes resolve and both land on or
before the cutoff. The existing guard deliberately lets missing metadata pass
("never block on missing metadata"), which is right for a live valuation and
wrong for a backtest: an undated input inside a replay is not evidence, it is
an unproven leak. ``unverifiable`` marks that case so callers can abstain.

Nothing here is a substitute for :class:`app.valuation.point_in_time.
LookaheadError`; these helpers raise the same exception so a caller holding a
single ``except LookaheadError`` still catches a bound violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.valuation.point_in_time import LookaheadError

PRECISION_EXACT_DATE = "exact_date"
PRECISION_FISCAL_YEAR = "fiscal_year"
PRECISION_UNKNOWN = "unknown"

# Calendar quarter ends, used to turn "Q3" + fiscal_year into a real date.
_QUARTER_END = {"Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)}

# "2025-12-31", optionally with a trailing period label: "2025-12-31:FY".
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")

# A bare 4-digit year, optionally prefixed by FY or followed by a quarter: the
# "FY2025" / "2025 Q3" shapes. Deliberately not anchored to a word boundary so
# "TTM-2025" and "FY2025" both resolve.
_YEAR_RE = re.compile(r"(?<!\d)(19|20)(\d{2})(?!\d)")

_QUARTER_RE = re.compile(r"Q([1-4])", re.IGNORECASE)


@dataclass(frozen=True)
class PeriodBounds:
    """The latest date a period can possibly have ended, and how sure we are."""

    raw: str | None = None
    end_date: date | None = None
    fiscal_year: int | None = None
    precision: str = PRECISION_UNKNOWN

    @property
    def is_unverifiable(self) -> bool:
        return self.precision == PRECISION_UNKNOWN or self.end_date is None

    def as_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "fiscal_year": self.fiscal_year,
            "precision": self.precision,
        }


@dataclass(frozen=True)
class KnowledgeBounds:
    """Period axis + publication axis: when an input became knowable."""

    period: PeriodBounds
    published_on: date | None = None

    @property
    def known_on(self) -> date | None:
        """Latest date the input could have been observed, or ``None``.

        ``None`` means "we cannot prove this input was public": either the
        period is unreadable or the source declares no publication date. A
        replay must abstain rather than assume.
        """
        if self.period.end_date is None or self.published_on is None:
            return None
        return max(self.period.end_date, self.published_on)

    @property
    def unverifiable(self) -> bool:
        return self.known_on is None or self.published_on is None

    def as_dict(self) -> dict[str, object]:
        return {
            "period": self.period.as_dict(),
            "published_on": self.published_on.isoformat() if self.published_on else None,
            "known_on": self.known_on.isoformat() if self.known_on else None,
            "unverifiable": self.unverifiable,
        }


AS_OF_SOURCE_EXPLICIT = "explicit"
AS_OF_SOURCE_VALUATION = "valuation.as_of"
AS_OF_SOURCE_TRACE = "trace.as_of"
AS_OF_SOURCE_TODAY_DEFAULT = "AS_OF_SOURCE_TODAY_DEFAULT"


@dataclass(frozen=True)
class AsOfResolution:
    """The cutoff actually used, and whether anyone asked for it."""

    cutoff: date
    source: str
    inferred: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "as_of": self.cutoff.isoformat(),
            "as_of_source": self.source,
            "as_of_inferred": self.inferred,
        }


def to_date(value: object) -> date | None:
    """Best-effort ISO date coercion; ``None`` instead of raising."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _quarter_end(fiscal_year: int, fiscal_quarter: str | None) -> date | None:
    if not fiscal_quarter:
        return None
    match = _QUARTER_RE.search(fiscal_quarter)
    if match is None:
        return None
    month, day = _QUARTER_END[f"Q{match.group(1)}"]
    return date(fiscal_year, month, day)


def parse_period_bounds(
    *,
    period: str | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: str | None = None,
) -> PeriodBounds:
    """Resolve a free-text period into an end date with an explicit precision.

    Precedence, most precise first:

    1. an ISO date inside ``period`` -> ``exact_date``;
    2. ``fiscal_year`` + a quarter -> the calendar quarter end -> ``exact_date``;
    3. ``fiscal_year`` alone -> 31 December of that year -> ``fiscal_year``;
    4. a bare 4-digit year inside ``period`` -> ``fiscal_year``;
    5. nothing usable -> ``unknown``.

    Step 3 is deliberately the *conservative* bound: December is the latest a
    fiscal year can end, so a fact we cannot place more precisely is assumed to
    have been known as late as possible. That direction can only turn a replay
    into ``insufficient_data``; the opposite would leak the future.
    """
    raw = (period or "").strip() or None

    if raw:
        iso = _ISO_DATE_RE.search(raw)
        if iso is not None:
            parsed = to_date(iso.group(1))
            if parsed is not None:
                return PeriodBounds(
                    raw=raw,
                    end_date=parsed,
                    fiscal_year=fiscal_year if fiscal_year is not None else parsed.year,
                    precision=PRECISION_EXACT_DATE,
                )

    if fiscal_year is not None:
        quarter_end = _quarter_end(fiscal_year, fiscal_quarter)
        if quarter_end is not None:
            return PeriodBounds(
                raw=raw,
                end_date=quarter_end,
                fiscal_year=fiscal_year,
                precision=PRECISION_EXACT_DATE,
            )
        return PeriodBounds(
            raw=raw,
            end_date=date(fiscal_year, 12, 31),
            fiscal_year=fiscal_year,
            precision=PRECISION_FISCAL_YEAR,
        )

    if raw:
        year_match = _YEAR_RE.search(raw)
        if year_match is not None:
            year = int(year_match.group(0))
            quarter_end = _quarter_end(year, raw)
            if quarter_end is not None:
                return PeriodBounds(
                    raw=raw,
                    end_date=quarter_end,
                    fiscal_year=year,
                    precision=PRECISION_EXACT_DATE,
                )
            return PeriodBounds(
                raw=raw,
                end_date=date(year, 12, 31),
                fiscal_year=year,
                precision=PRECISION_FISCAL_YEAR,
            )

    return PeriodBounds(raw=raw, end_date=None, fiscal_year=None, precision=PRECISION_UNKNOWN)


def knowledge_bounds(
    *,
    period: str | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: str | None = None,
    published_at: object = None,
) -> KnowledgeBounds:
    """Combine the period axis with the source document's publication date."""
    return KnowledgeBounds(
        period=parse_period_bounds(
            period=period, fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
        ),
        published_on=to_date(published_at),
    )


def assert_period_no_lookahead(*, as_of: date, bounds: PeriodBounds, label: str) -> None:
    """Raise when the period ends after ``as_of``.

    An ``unknown`` bound does NOT raise: it is not proof of a future date, it is
    an absence of proof. Callers in a replay must handle it through
    :attr:`PeriodBounds.is_unverifiable` instead of pretending it is fine.
    """
    if bounds.end_date is not None and bounds.end_date > as_of:
        raise LookaheadError(
            f"{label} termina en {bounds.end_date.isoformat()} ({bounds.raw!r}) "
            f"despues de as_of {as_of.isoformat()}; usarlo seria look-ahead"
        )


def assert_publication_no_lookahead(
    *, as_of: date, published_on: date | None, label: str
) -> None:
    """Raise when a source was published after ``as_of``.

    This is the axis a period-end guard cannot see: a FY2024 filing that lands
    in 2026 passes every fiscal-year check and still invalidates a 2025 replay.
    """
    if published_on is not None and published_on > as_of:
        raise LookaheadError(
            f"{label} se publico el {published_on.isoformat()}, despues de as_of "
            f"{as_of.isoformat()}; en esa fecha aun no era publico"
        )


def assert_knowledge_no_lookahead(*, as_of: date, bounds: KnowledgeBounds, label: str) -> None:
    """Both axes, in one call. Raises the first violation found."""
    assert_period_no_lookahead(as_of=as_of, bounds=bounds.period, label=label)
    assert_publication_no_lookahead(
        as_of=as_of, published_on=bounds.published_on, label=f"{label} (fuente)"
    )


def resolve_as_of(
    *,
    as_of: object = None,
    valuation: dict | None = None,
    trace: dict | None = None,
    today: date | None = None,
) -> AsOfResolution:
    """Resolve the cutoff, recording whether it was asked for or defaulted.

    Precedence: explicit argument, then ``valuation["as_of"]``, then
    ``trace["as_of"]``, then ``trace["snapshot"]["as_of"]``, then today. The
    last branch is the one a report must surface: a cell computed with
    ``AS_OF_SOURCE_TODAY_DEFAULT`` was *not* a replay of that day, it was a
    valuation with no date attached.
    """
    snapshot_as_of = ((trace or {}).get("snapshot") or {}).get("as_of")
    for value, source in (
        (as_of, AS_OF_SOURCE_EXPLICIT),
        ((valuation or {}).get("as_of"), AS_OF_SOURCE_VALUATION),
        ((trace or {}).get("as_of"), AS_OF_SOURCE_TRACE),
        (snapshot_as_of, AS_OF_SOURCE_TRACE),
    ):
        parsed = to_date(value)
        if parsed is not None:
            return AsOfResolution(cutoff=parsed, source=source, inferred=False)
    return AsOfResolution(
        cutoff=today or date.today(),
        source=AS_OF_SOURCE_TODAY_DEFAULT,
        inferred=True,
    )
