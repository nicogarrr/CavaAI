"""tenant isolation and research automation

Revision ID: 0004_research_automation
Revises: 0003_calculated_metrics
Create Date: 2026-07-09 23:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_research_automation"
down_revision = "0003_calculated_metrics"
branch_labels = None
depends_on = None


TENANT_OWNED_TABLES = [
    "positions",
    "cash_balances",
    "transactions",
    "documents",
    "financial_facts",
    "calculated_metrics",
    "financial_statements",
    "news_events",
    "external_claims",
    "transcripts",
    "call_claims",
    "catalysts",
    "valuation_models",
    "valuation_assumptions",
    "valuation_outputs",
    "thesis_versions",
    "thesis_diffs",
    "thesis_sections",
    "claims",
    "claim_evidence",
    "thesis_changes",
    "research_sessions",
    "memory_items",
    "source_audits",
    "risk_events",
    "daily_briefs",
    "chat_sessions",
    "model_runs",
    "budget_usage",
]


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "tenants" not in existing_tables:
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
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())

    for table_name in TENANT_OWNED_TABLES:
        if table_name not in existing_tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            with op.batch_alter_table(table_name) as batch:
                batch.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
            inspector = sa.inspect(bind)
        index_name = f"ix_{table_name}_tenant_id"
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, ["tenant_id"], unique=False)
            inspector = sa.inspect(bind)

    op.create_table(
        "connector_states",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("connector", sa.String(80), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("feed_url", sa.String(1000), nullable=True),
        sa.Column("cursor", sa.String(500), nullable=True),
        sa.Column("etag", sa.String(300), nullable=True),
        sa.Column("last_modified", sa.String(300), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "connector", "company_id", "feed_url", name="uq_connector_state"),
    )
    op.create_index("ix_connector_states_connector", "connector_states", ["connector"], unique=False)
    op.create_index("ix_connector_states_tenant_id", "connector_states", ["tenant_id"], unique=False)

    op.create_table(
        "moat_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("moat_type", sa.String(80), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False),
        sa.Column("trend", sa.String(40), nullable=False),
        sa.Column("persistence", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("supporting_claim_ids", sa.JSON(), nullable=False),
        sa.Column("contradicting_claim_ids", sa.JSON(), nullable=False),
        sa.Column("assessment_trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "moat_type", name="uq_tenant_company_moat_type"),
    )
    op.create_index("ix_moat_assessments_company_id", "moat_assessments", ["company_id"], unique=False)
    op.create_index("ix_moat_assessments_tenant_id", "moat_assessments", ["tenant_id"], unique=False)

    op.create_table(
        "peer_relationships",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("peer_company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("score", sa.Numeric(6, 4), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("selection_trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "peer_company_id", name="uq_tenant_company_peer_relationship"),
    )
    op.create_index("ix_peer_relationships_company_id", "peer_relationships", ["company_id"], unique=False)
    op.create_index("ix_peer_relationships_peer_company_id", "peer_relationships", ["peer_company_id"], unique=False)
    op.create_index("ix_peer_relationships_tenant_id", "peer_relationships", ["tenant_id"], unique=False)

    op.create_table(
        "red_team_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("strongest_bear_case", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("broken_assumptions", sa.JSON(), nullable=False),
        sa.Column("missing_risks", sa.JSON(), nullable=False),
        sa.Column("falsification_tests", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_red_team_runs_company_id", "red_team_runs", ["company_id"], unique=False)
    op.create_index("ix_red_team_runs_tenant_id", "red_team_runs", ["tenant_id"], unique=False)
    op.create_index("ix_red_team_runs_thesis_version_id", "red_team_runs", ["thesis_version_id"], unique=False)

    op.create_table(
        "thesis_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=False),
        sa.Column("node_key", sa.String(160), nullable=False),
        sa.Column("node_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("materiality_score", sa.Integer(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("invalidation_conditions", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("thesis_version_id", "node_key", name="uq_thesis_node_version_key"),
    )
    op.create_index("ix_thesis_nodes_company_id", "thesis_nodes", ["company_id"], unique=False)
    op.create_index("ix_thesis_nodes_tenant_id", "thesis_nodes", ["tenant_id"], unique=False)
    op.create_index("ix_thesis_nodes_thesis_version_id", "thesis_nodes", ["thesis_version_id"], unique=False)

    op.create_table(
        "earnings_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.String(10), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("extracted_metrics", sa.JSON(), nullable=False),
        sa.Column("guidance_changes", sa.JSON(), nullable=False),
        sa.Column("comparisons", sa.JSON(), nullable=False),
        sa.Column("management_tone", sa.JSON(), nullable=False),
        sa.Column("promise_tracking", sa.JSON(), nullable=False),
        sa.Column("risk_updates", sa.JSON(), nullable=False),
        sa.Column("catalyst_updates", sa.JSON(), nullable=False),
        sa.Column("claim_changes", sa.JSON(), nullable=False),
        sa.Column("thesis_change_id", sa.Integer(), sa.ForeignKey("thesis_changes.id"), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_earnings_runs_company_id", "earnings_runs", ["company_id"], unique=False)
    op.create_index("ix_earnings_runs_status", "earnings_runs", ["status"], unique=False)
    op.create_index("ix_earnings_runs_tenant_id", "earnings_runs", ["tenant_id"], unique=False)

    op.create_table(
        "evidence_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("document_chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=True),
        sa.Column("suggested_claim_id", sa.Integer(), sa.ForeignKey("claims.id"), nullable=True),
        sa.Column("suggestion_type", sa.String(80), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("relation", sa.String(40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_suggestions_company_id", "evidence_suggestions", ["company_id"], unique=False)
    op.create_index("ix_evidence_suggestions_document_chunk_id", "evidence_suggestions", ["document_chunk_id"], unique=False)
    op.create_index("ix_evidence_suggestions_tenant_id", "evidence_suggestions", ["tenant_id"], unique=False)

    op.create_table(
        "research_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("review_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(40), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("thesis_change_id", sa.Integer(), sa.ForeignKey("thesis_changes.id"), nullable=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id"), nullable=True),
        sa.Column("news_event_id", sa.Integer(), sa.ForeignKey("news_events.id"), nullable=True),
        sa.Column("assigned_to", sa.String(160), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_reviews_company_id", "research_reviews", ["company_id"], unique=False)
    op.create_index("ix_research_reviews_review_type", "research_reviews", ["review_type"], unique=False)
    op.create_index("ix_research_reviews_status", "research_reviews", ["status"], unique=False)
    op.create_index("ix_research_reviews_tenant_id", "research_reviews", ["tenant_id"], unique=False)

    op.create_table(
        "thesis_edges",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("from_node_id", sa.Integer(), sa.ForeignKey("thesis_nodes.id"), nullable=False),
        sa.Column("to_node_id", sa.Integer(), sa.ForeignKey("thesis_nodes.id"), nullable=False),
        sa.Column("edge_type", sa.String(80), nullable=False),
        sa.Column("strength", sa.Numeric(5, 4), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("from_node_id", "to_node_id", "edge_type", name="uq_thesis_edge"),
    )
    op.create_index("ix_thesis_edges_from_node_id", "thesis_edges", ["from_node_id"], unique=False)
    op.create_index("ix_thesis_edges_tenant_id", "thesis_edges", ["tenant_id"], unique=False)
    op.create_index("ix_thesis_edges_to_node_id", "thesis_edges", ["to_node_id"], unique=False)

    op.create_table(
        "research_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("research_reviews.id"), nullable=True),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("alert_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(160), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(160), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "fingerprint", name="uq_research_alert_fingerprint"),
    )
    op.create_index("ix_research_alerts_alert_type", "research_alerts", ["alert_type"], unique=False)
    op.create_index("ix_research_alerts_company_id", "research_alerts", ["company_id"], unique=False)
    op.create_index("ix_research_alerts_severity", "research_alerts", ["severity"], unique=False)
    op.create_index("ix_research_alerts_status", "research_alerts", ["status"], unique=False)
    op.create_index("ix_research_alerts_tenant_id", "research_alerts", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("research_alerts")
    op.drop_table("thesis_edges")
    op.drop_table("research_reviews")
    op.drop_table("evidence_suggestions")
    op.drop_table("earnings_runs")
    op.drop_table("thesis_nodes")
    op.drop_table("red_team_runs")
    op.drop_table("peer_relationships")
    op.drop_table("moat_assessments")
    op.drop_table("connector_states")
