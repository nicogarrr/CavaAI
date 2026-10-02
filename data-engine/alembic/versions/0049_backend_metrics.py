"""Metricas de backend: latencia por endpoint, profundidad de cola, hit-rate de
tesis y % de claims con evidencia (#E5).

Cuatro tablas agregadas, ninguna con PII y ninguna con un log por peticion:

- ``api_latency_windows``: una fila por (tenant, ventana, ruta, metodo, codigo)
  con contadores y un histograma de 18 cajones. El histograma esta en columnas y
  no en un JSON a proposito: asi el UPSERT del recorder puede sumar un cajon en
  SQL atomico, mientras que un JSON obligaria a leer-modificar-escribir.
- ``queue_depth_snapshots``: plataforma, SIN tenant_id. Las colas de Dramatiq no
  se particionan por tenant; anadir la columna seria fingir un aislamiento que
  no existe.
- ``thesis_hit_rate_cells``: numerador, denominador y un contador por motivo de
  exclusion en la MISMA fila, mas el snapshot de la regla con la que se calculo.
- ``evidence_coverage_snapshots``: la media de cobertura con su p10/p50/p90 y su
  histograma, porque la media sola puede mentir.

Los timestamps son ``timestamp without time zone`` y se escriben siempre en UTC
naive (ver ``app/models/metrics.py``): la zona la fija el modulo, no la sesion
de la BD, para que la misma fila se lea igual en Postgres y en SQLite.
"""
import sqlalchemy as sa

from alembic import op

revision = "0049_backend_metrics"
down_revision = "0048_thesis_realized_return"
branch_labels = None
depends_on = None


def _bucket_columns() -> list:
    """Los 17 cajones del histograma, en el MISMO orden que LATENCY_BUCKET_EDGES."""
    edges = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
             30000, 60000, 120000, 300000)
    return [sa.Column(f"le_{edge}", sa.Integer(), nullable=False, server_default="0")
            for edge in edges]


def upgrade() -> None:
    op.create_table(
        "api_latency_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=False), nullable=False),
        sa.Column("window_size", sa.String(10), nullable=False, server_default="hour"),
        sa.Column("route_template", sa.String(200), nullable=False, server_default=""),
        sa.Column("method", sa.String(10), nullable=False, server_default="GET"),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_sum_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overhead_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overhead_sum_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overhead_max_ms", sa.Float(), nullable=False, server_default="0"),
        *_bucket_columns(),
        sa.Column("overflow", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "window_start", "window_size", "route_template", "method",
            "status_code", name="uq_api_latency_window",
        ),
    )
    op.create_index("ix_api_latency_windows_tenant_id", "api_latency_windows", ["tenant_id"])
    op.create_index("ix_api_latency_windows_window_start", "api_latency_windows",
                    ["window_start"])
    op.create_index(
        "ix_api_latency_windows_tenant_window", "api_latency_windows",
        ["tenant_id", "window_start"],
    )
    op.create_index(
        "ix_api_latency_windows_route", "api_latency_windows",
        ["route_template", "window_start"],
    )

    op.create_table(
        "queue_depth_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_name", sa.String(80), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=False), nullable=False),
        sa.Column("window_size", sa.String(10), nullable=False, server_default="hour"),
        # Los cuatro contadores son NULLABLE y sin server_default: NULL es "no
        # se pudo medir" (Redis caido) y tiene que sobrevivir al round-trip. Con
        # server_default="0" un NULL se convertiria en un 0 mentiroso.
        sa.Column("pending", sa.Integer(), nullable=True),
        sa.Column("delayed", sa.Integer(), nullable=True),
        sa.Column("in_flight", sa.Integer(), nullable=True),
        sa.Column("dead_lettered", sa.Integer(), nullable=True),
        sa.Column("oldest_age_s", sa.Float(), nullable=True),
        sa.Column("oldest_age_exhaustive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oldest_age_sample", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("workers_live", sa.Integer(), nullable=True),
        sa.Column("workers_total", sa.Integer(), nullable=True),
        sa.Column("newest_heartbeat_age_s", sa.Float(), nullable=True),
        sa.Column("processed", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("skipped", sa.Integer(), nullable=True),
        sa.Column("retried", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="desconocido"),
        sa.Column("incident_reason", sa.String(255), nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="redis"),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
    )
    op.create_index("ix_queue_depth_snapshots_queue_name", "queue_depth_snapshots",
                    ["queue_name"])
    op.create_index("ix_queue_depth_snapshots_observed_at", "queue_depth_snapshots",
                    ["observed_at"])
    op.create_index(
        "ix_queue_depth_snapshots_queue_time", "queue_depth_snapshots",
        ["queue_name", "observed_at"],
    )
    op.create_index(
        "ix_queue_depth_snapshots_window", "queue_depth_snapshots",
        ["window_start", "window_size"],
    )

    op.create_table(
        "thesis_hit_rate_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(40), nullable=False, server_default="*"),
        sa.Column("sector", sa.String(120), nullable=False, server_default="*"),
        sa.Column("evidence_bucket", sa.String(40), nullable=False, server_default="*"),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("misses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_neutral", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_rating_unknown", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_no_entry_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_no_exit_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_too_early", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_tie", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_no_benchmark", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_rate", sa.Float(), nullable=True),
        sa.Column("avg_return", sa.Float(), nullable=True),
        sa.Column("median_return", sa.Float(), nullable=True),
        sa.Column("p10_return", sa.Float(), nullable=True),
        sa.Column("p90_return", sa.Float(), nullable=True),
        sa.Column("benchmark_ticker", sa.String(20), nullable=True),
        sa.Column("benchmark_return", sa.Float(), nullable=True),
        sa.Column("alpha", sa.Float(), nullable=True),
        sa.Column("benchmark_status", sa.String(20), nullable=False, server_default="N/D"),
        sa.Column("benchmark_reason", sa.String(160), nullable=True),
        sa.Column("definitions", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "as_of", "horizon_days", "decision", "sector", "evidence_bucket",
            name="uq_thesis_hit_rate_cell",
        ),
    )
    op.create_index("ix_thesis_hit_rate_cells_tenant_id", "thesis_hit_rate_cells", ["tenant_id"])
    op.create_index("ix_thesis_hit_rate_cells_as_of", "thesis_hit_rate_cells", ["as_of"])
    op.create_index(
        "ix_thesis_hit_rate_cells_tenant_as_of", "thesis_hit_rate_cells",
        ["tenant_id", "as_of"],
    )

    op.create_table(
        "evidence_coverage_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(40), nullable=False, server_default="global"),
        sa.Column("claims_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claims_with_evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_claims", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_with_evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_with_official", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_with_inferred", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_without_evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thesis_versions_considered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_p10", sa.Float(), nullable=True),
        sa.Column("coverage_p50", sa.Float(), nullable=True),
        sa.Column("coverage_p90", sa.Float(), nullable=True),
        sa.Column("coverage_mean", sa.Float(), nullable=True),
        sa.Column("coverage_histogram", sa.JSON(), nullable=False),
        sa.Column("score_p10", sa.Float(), nullable=True),
        sa.Column("score_p50", sa.Float(), nullable=True),
        sa.Column("score_p90", sa.Float(), nullable=True),
        sa.Column("score_histogram", sa.JSON(), nullable=False),
        sa.Column("audits_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audits_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsupported_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weak_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_conflicts_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_fixes_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auditor_mean_coverage", sa.Float(), nullable=True),
        sa.Column("materiality_threshold", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "as_of", "scope", name="uq_evidence_coverage_snapshot",
        ),
    )
    op.create_index(
        "ix_evidence_coverage_snapshots_tenant_id", "evidence_coverage_snapshots", ["tenant_id"]
    )
    op.create_index("ix_evidence_coverage_snapshots_as_of", "evidence_coverage_snapshots",
                    ["as_of"])
    op.create_index(
        "ix_evidence_coverage_tenant_as_of", "evidence_coverage_snapshots",
        ["tenant_id", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_coverage_tenant_as_of",
                  table_name="evidence_coverage_snapshots")
    op.drop_index("ix_evidence_coverage_snapshots_as_of",
                  table_name="evidence_coverage_snapshots")
    op.drop_index("ix_evidence_coverage_snapshots_tenant_id",
                  table_name="evidence_coverage_snapshots")
    op.drop_table("evidence_coverage_snapshots")

    op.drop_index("ix_thesis_hit_rate_cells_tenant_as_of", table_name="thesis_hit_rate_cells")
    op.drop_index("ix_thesis_hit_rate_cells_as_of", table_name="thesis_hit_rate_cells")
    op.drop_index("ix_thesis_hit_rate_cells_tenant_id", table_name="thesis_hit_rate_cells")
    op.drop_table("thesis_hit_rate_cells")

    op.drop_index("ix_queue_depth_snapshots_window", table_name="queue_depth_snapshots")
    op.drop_index("ix_queue_depth_snapshots_queue_time", table_name="queue_depth_snapshots")
    op.drop_index("ix_queue_depth_snapshots_observed_at", table_name="queue_depth_snapshots")
    op.drop_index("ix_queue_depth_snapshots_queue_name", table_name="queue_depth_snapshots")
    op.drop_table("queue_depth_snapshots")

    op.drop_index("ix_api_latency_windows_route", table_name="api_latency_windows")
    op.drop_index("ix_api_latency_windows_tenant_window", table_name="api_latency_windows")
    op.drop_index("ix_api_latency_windows_window_start", table_name="api_latency_windows")
    op.drop_index("ix_api_latency_windows_tenant_id", table_name="api_latency_windows")
    op.drop_table("api_latency_windows")