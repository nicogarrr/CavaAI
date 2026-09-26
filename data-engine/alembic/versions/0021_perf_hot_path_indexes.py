"""indices compuestos para rutas calientes (anti N+1 / full scans).

Revision ID: 0021_perf_hot_path_indexes
Revises: 0020_news_event_metadata
"""

from alembic import op

revision = "0021_perf_hot_path_indexes"
down_revision = "0020_news_event_metadata"
branch_labels = None
depends_on = None


INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_fx_rates_base_quote_date", "fx_rates", ["base_currency", "quote_currency", "rate_date"]),
    ("ix_positions_portfolio_company", "positions", ["portfolio_id", "company_id"]),
    ("ix_transactions_portfolio_trade_date", "transactions", ["portfolio_id", "trade_date"]),
    ("ix_transactions_company_action", "transactions", ["company_id", "action"]),
    ("ix_portfolio_snapshots_portfolio_date", "portfolio_daily_snapshots", ["portfolio_id", "snapshot_date"]),
    ("ix_documents_company_id", "documents", ["company_id"]),
    ("ix_document_chunks_doc_idx", "document_chunks", ["document_id", "chunk_index"]),
    ("ix_financial_facts_company_metric_year", "financial_facts", ["company_id", "metric", "fiscal_year"]),
    ("ix_calculated_metrics_company_metric", "calculated_metrics", ["company_id", "metric"]),
    ("ix_valuation_models_company_version", "valuation_models", ["company_id", "version"]),
    ("ix_thesis_versions_company_version", "thesis_versions", ["company_id", "version"]),
    ("ix_claims_company_status", "claims", ["company_id", "status"]),
    ("ix_thesis_changes_company_created", "thesis_changes", ["company_id", "created_at"]),
    ("ix_research_reviews_company_status", "research_reviews", ["company_id", "status"]),
    ("ix_research_alerts_company_status", "research_alerts", ["company_id", "status"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
