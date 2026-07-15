"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-03 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("sector", sa.String(120), nullable=False),
        sa.Column("industry", sa.String(160), nullable=False),
        sa.Column("cik", sa.String(20), nullable=True),
        sa.Column("ir_url", sa.String(500), nullable=True),
        sa.Column("company_type", sa.String(80), nullable=False),
        sa.Column("valuation_model", sa.String(120), nullable=False),
        sa.Column("special_sources", sa.JSON(), nullable=False),
        sa.Column("special_risks", sa.JSON(), nullable=False),
        sa.Column("factor_tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"], unique=True)

    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_external_id", "tenants", ["external_id"], unique=True)

    op.create_table(
        "budget_usage",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("workflow", sa.String(120), nullable=False),
        sa.Column("cost_eur", sa.Numeric(12, 6), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_budget_usage_tenant_id", "budget_usage", ["tenant_id"], unique=False)
    op.create_index("ix_budget_usage_usage_date", "budget_usage", ["usage_date"], unique=False)

    op.create_table(
        "cash_balances",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("settled_cash", sa.Numeric(20, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cash_balances_currency", "cash_balances", ["currency"], unique=False)
    op.create_index("ix_cash_balances_tenant_id", "cash_balances", ["tenant_id"], unique=False)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"], unique=False)

    op.create_table(
        "daily_briefs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("alerts", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "brief_date", name="uq_daily_brief_tenant_date"),
    )
    op.create_index("ix_daily_briefs_tenant_id", "daily_briefs", ["tenant_id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("storage_uri", sa.String(1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_source_type", "documents", ["source_type"], unique=False)
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"], unique=False)

    op.create_table(
        "market_prices",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=False),
        sa.Column("high", sa.Numeric(20, 6), nullable=False),
        sa.Column("low", sa.Numeric(20, 6), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("adj_close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "date", name="uq_market_price_company_date"),
    )
    op.create_index("ix_market_prices_company_id", "market_prices", ["company_id"], unique=False)
    op.create_index("ix_market_prices_date", "market_prices", ["date"], unique=False)

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("workflow", sa.String(120), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_runs_tenant_id", "model_runs", ["tenant_id"], unique=False)
    op.create_index("ix_model_runs_workflow", "model_runs", ["workflow"], unique=False)

    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("materiality_score", sa.Integer(), nullable=False),
        sa.Column("impact_direction", sa.String(40), nullable=False),
        sa.Column("affected_thesis", sa.Boolean(), nullable=False),
        sa.Column("affected_assumptions", sa.JSON(), nullable=False),
        sa.Column("requires_update", sa.Boolean(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_news_events_tenant_id", "news_events", ["tenant_id"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("average_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("market_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(20, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_positions_company_id", "positions", ["company_id"], unique=False)
    op.create_index("ix_positions_tenant_id", "positions", ["tenant_id"], unique=False)

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("threshold", sa.Numeric(20, 6), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_events_tenant_id", "risk_events", ["tenant_id"], unique=False)

    op.create_table(
        "thesis_versions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("thesis_markdown", sa.Text(), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("rating", sa.String(40), nullable=False),
        sa.Column("current_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("bear_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("base_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("bull_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("expected_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("margin_of_safety", sa.Numeric(12, 6), nullable=False),
        sa.Column("data_confidence_score", sa.Integer(), nullable=False),
        sa.Column("source_coverage_score", sa.Integer(), nullable=False),
        sa.Column("red_team_score", sa.Integer(), nullable=False),
        sa.Column("valuation_risk_score", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "version", name="uq_thesis_tenant_company_version"),
    )
    op.create_index("ix_thesis_versions_company_id", "thesis_versions", ["company_id"], unique=False)
    op.create_index("ix_thesis_versions_input_fingerprint", "thesis_versions", ["input_fingerprint"], unique=False)
    op.create_index("ix_thesis_versions_tenant_id", "thesis_versions", ["tenant_id"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.Column("fees", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_transaction_tenant_external"),
    )
    op.create_index("ix_transactions_tenant_id", "transactions", ["tenant_id"], unique=False)
    op.create_index("ix_transactions_trade_date", "transactions", ["trade_date"], unique=False)

    op.create_table(
        "valuation_models",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("model_type", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("calculation_trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_valuation_models_company_id", "valuation_models", ["company_id"], unique=False)
    op.create_index("ix_valuation_models_tenant_id", "valuation_models", ["tenant_id"], unique=False)

    op.create_table(
        "catalysts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("catalyst_type", sa.String(80), nullable=False),
        sa.Column("materiality_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalysts_company_id", "catalysts", ["company_id"], unique=False)
    op.create_index("ix_catalysts_tenant_id", "catalysts", ["tenant_id"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"], unique=False)

    op.create_table(
        "external_claims",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("metric", sa.String(120), nullable=True),
        sa.Column("period", sa.String(40), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("used_in_model", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_claims_tenant_id", "external_claims", ["tenant_id"], unique=False)

    op.create_table(
        "financial_facts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("metric", sa.String(120), nullable=False),
        sa.Column("value", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("is_reported", sa.Boolean(), nullable=False),
        sa.Column("is_adjusted", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_financial_facts_company_id", "financial_facts", ["company_id"], unique=False)
    op.create_index("ix_financial_facts_metric", "financial_facts", ["metric"], unique=False)
    op.create_index("ix_financial_facts_tenant_id", "financial_facts", ["tenant_id"], unique=False)

    op.create_table(
        "financial_statements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("statement_type", sa.String(40), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_financial_statements_company_id", "financial_statements", ["company_id"], unique=False)
    op.create_index("ix_financial_statements_tenant_id", "financial_statements", ["tenant_id"], unique=False)

    op.create_table(
        "source_audits",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("source_coverage_score", sa.Integer(), nullable=False),
        sa.Column("unsupported_claims", sa.JSON(), nullable=False),
        sa.Column("weak_claims", sa.JSON(), nullable=False),
        sa.Column("data_conflicts", sa.JSON(), nullable=False),
        sa.Column("required_fixes", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_audits_tenant_id", "source_audits", ["tenant_id"], unique=False)

    op.create_table(
        "thesis_diffs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("from_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("to_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("affected_assumptions", sa.JSON(), nullable=False),
        sa.Column("rating_changed", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_thesis_diffs_company_id", "thesis_diffs", ["company_id"], unique=False)
    op.create_index("ix_thesis_diffs_tenant_id", "thesis_diffs", ["tenant_id"], unique=False)

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transcripts_company_id", "transcripts", ["company_id"], unique=False)
    op.create_index("ix_transcripts_tenant_id", "transcripts", ["tenant_id"], unique=False)

    op.create_table(
        "valuation_assumptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("valuation_model_id", sa.Integer(), sa.ForeignKey("valuation_models.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("scenario", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("assumption_type", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("is_user_override", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_valuation_assumptions_tenant_id", "valuation_assumptions", ["tenant_id"], unique=False)
    op.create_index("ix_valuation_assumptions_valuation_model_id", "valuation_assumptions", ["valuation_model_id"], unique=False)

    op.create_table(
        "valuation_outputs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("valuation_model_id", sa.Integer(), sa.ForeignKey("valuation_models.id"), nullable=False),
        sa.Column("scenario", sa.String(40), nullable=False),
        sa.Column("equity_value", sa.Numeric(24, 2), nullable=False),
        sa.Column("value_per_share", sa.Numeric(20, 4), nullable=False),
        sa.Column("margin_of_safety", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_valuation_outputs_tenant_id", "valuation_outputs", ["tenant_id"], unique=False)
    op.create_index("ix_valuation_outputs_valuation_model_id", "valuation_outputs", ["valuation_model_id"], unique=False)

    op.create_table(
        "call_claims",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("transcript_id", sa.Integer(), sa.ForeignKey("transcripts.id"), nullable=False),
        sa.Column("speaker", sa.String(160), nullable=False),
        sa.Column("speaker_role", sa.String(120), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("metric", sa.String(120), nullable=True),
        sa.Column("period", sa.String(40), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("follow_up_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("later_verified", sa.Boolean(), nullable=True),
        sa.Column("linked_result_id", sa.Integer(), sa.ForeignKey("financial_facts.id"), nullable=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_call_claims_tenant_id", "call_claims", ["tenant_id"], unique=False)
    op.create_index("ix_call_claims_transcript_id", "call_claims", ["transcript_id"], unique=False)


def downgrade() -> None:
    op.drop_table("call_claims")
    op.drop_table("valuation_outputs")
    op.drop_table("valuation_assumptions")
    op.drop_table("transcripts")
    op.drop_table("thesis_diffs")
    op.drop_table("source_audits")
    op.drop_table("financial_statements")
    op.drop_table("financial_facts")
    op.drop_table("external_claims")
    op.drop_table("document_chunks")
    op.drop_table("catalysts")
    op.drop_table("valuation_models")
    op.drop_table("transactions")
    op.drop_table("thesis_versions")
    op.drop_table("risk_events")
    op.drop_table("positions")
    op.drop_table("news_events")
    op.drop_table("model_runs")
    op.drop_table("market_prices")
    op.drop_table("documents")
    op.drop_table("daily_briefs")
    op.drop_table("chat_sessions")
    op.drop_table("cash_balances")
    op.drop_table("budget_usage")
    op.drop_table("tenants")
    op.drop_table("companies")
