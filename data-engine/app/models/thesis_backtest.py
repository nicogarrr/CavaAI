"""Persistence for point-in-time thesis backtests.

Three tables, one job: ``BacktestRun`` is the grid that was requested,
``BacktestCellRow`` is one (ticker, day) replay and ``BacktestResult`` is the
aggregated answer to "do the theses have alpha or only narrative coherence".

The cell table is the interesting one. It is keyed on
``(tenant_id, run_id, ticker, as_of)`` so re-running a grid updates rows instead
of appending duplicates: a backtest that cannot be replayed identically cannot
be trusted, and the ``cell_hash`` column makes that check a single equality
rather than a diff. Every numeric column is nullable on purpose — an abstention
stores ``NULL`` and a reason, never a zero and never the current price.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.entities import Base, TenantOwnedMixin, TimestampMixin

# Replay outcomes. The first three are abstentions: they must carry a reason and
# a NULL fair value, which is what the gates check.
STATUS_OK = "ok"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_NOT_YET_PUBLISHED = "not_yet_published"
STATUS_REJECTED_LOOKAHEAD = "rejected_lookahead"
STATUS_ERROR = "error"

ABSTENTION_STATUSES = (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NOT_YET_PUBLISHED,
    STATUS_REJECTED_LOOKAHEAD,
    STATUS_ERROR,
)


class BacktestRun(TenantOwnedMixin, Base, TimestampMixin):
    """One requested ticker x date grid."""

    __tablename__ = "thesis_backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tickers: Mapped[list] = mapped_column(JSON, default=list)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    step: Mapped[str] = mapped_column(String(8), default="1M")
    as_of_strategy: Mapped[str] = mapped_column(String(20), default="replay")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    cells_total: Mapped[int] = mapped_column(Integer, default=0)
    cells_done: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BacktestCellRow(TenantOwnedMixin, Base, TimestampMixin):
    """One replayed (ticker, as_of) cell, persisted verbatim."""

    __tablename__ = "thesis_backtest_cells"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "run_id", "ticker", "as_of", name="uq_backtest_cell_replay"
        ),
        Index("ix_backtest_cells_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("thesis_backtest_runs.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)

    status: Mapped[str] = mapped_column(String(32), default=STATUS_INSUFFICIENT_DATA)
    engine_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The date the evidence behind this cell was actually cut at. Always stored
    # next to the fair value: a number without its cutoff is not a result.
    evidence_cutoff: Mapped[date] = mapped_column(Date)

    fair_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bear_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    base_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    bull_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    current_price: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    upside: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_source: Mapped[str | None] = mapped_column(String(40), nullable=True)

    n_claims: Mapped[int] = mapped_column(Integer, default=0)
    n_claims_with_evidence: Mapped[int] = mapped_column(Integer, default=0)
    source_coverage_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    debate_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)

    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    lookahead_violations: Mapped[list] = mapped_column(JSON, default=list)
    # Future rows the filter found and refused. Distinct from violations: these
    # are the trap sprung correctly, and their absence would mean nobody looked.
    excluded_future_inputs: Mapped[list] = mapped_column(JSON, default=list)
    unverifiable_inputs: Mapped[list] = mapped_column(JSON, default=list)
    missing_inputs: Mapped[list] = mapped_column(JSON, default=list)
    publication_blockers: Mapped[list] = mapped_column(JSON, default=list)
    point_in_time: Mapped[dict] = mapped_column(JSON, default=dict)
    realized: Mapped[dict] = mapped_column(JSON, default=dict)
    claims: Mapped[list] = mapped_column(JSON, default=list)
    cell_hash: Mapped[str] = mapped_column(String(64), index=True)


class BacktestResult(TenantOwnedMixin, Base, TimestampMixin):
    """Aggregated metrics for a run: the answer to the alpha question."""

    __tablename__ = "thesis_backtest_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", name="uq_backtest_result_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("thesis_backtest_runs.id", ondelete="CASCADE"), index=True
    )
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = [
    "ABSTENTION_STATUSES",
    "BacktestCellRow",
    "BacktestResult",
    "BacktestRun",
    "STATUS_ERROR",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_NOT_YET_PUBLISHED",
    "STATUS_OK",
    "STATUS_REJECTED_LOOKAHEAD",
]
