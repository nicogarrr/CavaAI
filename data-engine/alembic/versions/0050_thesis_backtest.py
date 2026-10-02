"""Backtest point-in-time de tesis: rejilla, celdas y metricas agregadas."""
import sqlalchemy as sa

from alembic import op

revision = "0050_thesis_backtest"
down_revision = "0048_thesis_realized_return"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_backtest_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("step", sa.String(8), nullable=False, server_default="1M"),
        sa.Column(
            "as_of_strategy", sa.String(20), nullable=False, server_default="replay"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("cells_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cells_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_thesis_backtest_runs_tenant_id", "thesis_backtest_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_thesis_backtest_runs_status", "thesis_backtest_runs", ["status"]
    )

    # La clave unica (tenant, run, ticker, as_of) es el mecanismo de
    # idempotencia: relanzar la rejilla ACTUALIZA la celda en vez de duplicar
    # la fila, que es lo que hace auditable un backtest (celda + hash).
    op.create_table(
        "thesis_backtest_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("thesis_backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="insufficient_data"
        ),
        sa.Column("engine_key", sa.String(40), nullable=True),
        sa.Column("model_version", sa.String(40), nullable=True),
        sa.Column("evidence_cutoff", sa.Date(), nullable=False),
        sa.Column("fair_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("bear_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("base_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("bull_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("current_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("upside", sa.Numeric(12, 6), nullable=True),
        sa.Column("price_date", sa.Date(), nullable=True),
        sa.Column("price_source", sa.String(40), nullable=True),
        sa.Column("n_claims", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "n_claims_with_evidence", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("source_coverage_score", sa.Integer(), nullable=True),
        sa.Column("debate_verdict", sa.String(20), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("degraded_reason", sa.String(300), nullable=True),
        sa.Column("lookahead_violations", sa.JSON(), nullable=False),
        sa.Column("excluded_future_inputs", sa.JSON(), nullable=False),
        sa.Column("unverifiable_inputs", sa.JSON(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("publication_blockers", sa.JSON(), nullable=False),
        sa.Column("point_in_time", sa.JSON(), nullable=False),
        sa.Column("realized", sa.JSON(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("cell_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "ticker", "as_of", name="uq_backtest_cell_replay"
        ),
    )
    op.create_index(
        "ix_thesis_backtest_cells_tenant_id", "thesis_backtest_cells", ["tenant_id"]
    )
    op.create_index(
        "ix_thesis_backtest_cells_run_id", "thesis_backtest_cells", ["run_id"]
    )
    op.create_index(
        "ix_thesis_backtest_cells_ticker", "thesis_backtest_cells", ["ticker"]
    )
    op.create_index("ix_thesis_backtest_cells_as_of", "thesis_backtest_cells", ["as_of"])
    op.create_index(
        "ix_thesis_backtest_cells_cell_hash", "thesis_backtest_cells", ["cell_hash"]
    )
    op.create_index(
        "ix_backtest_cells_run_ticker",
        "thesis_backtest_cells",
        ["run_id", "ticker"],
    )

    op.create_table(
        "thesis_backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("thesis_backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "run_id", name="uq_backtest_result_run"
        ),
    )
    op.create_index(
        "ix_thesis_backtest_results_tenant_id", "thesis_backtest_results", ["tenant_id"]
    )
    op.create_index(
        "ix_thesis_backtest_results_run_id", "thesis_backtest_results", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_thesis_backtest_results_run_id", table_name="thesis_backtest_results")
    op.drop_index(
        "ix_thesis_backtest_results_tenant_id", table_name="thesis_backtest_results"
    )
    op.drop_table("thesis_backtest_results")

    op.drop_index("ix_backtest_cells_run_ticker", table_name="thesis_backtest_cells")
    op.drop_index("ix_thesis_backtest_cells_cell_hash", table_name="thesis_backtest_cells")
    op.drop_index("ix_thesis_backtest_cells_as_of", table_name="thesis_backtest_cells")
    op.drop_index("ix_thesis_backtest_cells_ticker", table_name="thesis_backtest_cells")
    op.drop_index("ix_thesis_backtest_cells_run_id", table_name="thesis_backtest_cells")
    op.drop_index(
        "ix_thesis_backtest_cells_tenant_id", table_name="thesis_backtest_cells"
    )
    op.drop_table("thesis_backtest_cells")

    op.drop_index("ix_thesis_backtest_runs_status", table_name="thesis_backtest_runs")
    op.drop_index("ix_thesis_backtest_runs_tenant_id", table_name="thesis_backtest_runs")
    op.drop_table("thesis_backtest_runs")
