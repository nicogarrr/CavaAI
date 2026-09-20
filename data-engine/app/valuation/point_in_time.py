"""Point-in-time guard against look-ahead bias.

Any valuation/backtest computed "as of" a date must only observe data that
existed on or before that date. Observing later data (future prices,
not-yet-published fundamentals) silently inflates backtest returns and
invalidates the analysis. These helpers fail loudly instead.
"""

from __future__ import annotations

from datetime import date


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
