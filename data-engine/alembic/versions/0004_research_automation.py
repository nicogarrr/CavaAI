"""tenant isolation and research automation

Revision ID: 0004_research_automation
Revises: 0003_calculated_metrics
Create Date: 2026-07-09 23:40:00
"""

from alembic import op
import sqlalchemy as sa

from app import models  # noqa: F401
from app.core.database import Base

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

NEW_TABLES = [
    "tenants",
    "evidence_suggestions",
    "research_reviews",
    "thesis_nodes",
    "thesis_edges",
    "research_alerts",
    "connector_states",
    "earnings_runs",
    "moat_assessments",
    "peer_relationships",
    "red_team_runs",
]


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["tenants"].create(bind=bind, checkfirst=True)

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

    for table_name in NEW_TABLES[1:]:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES[1:]):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in reversed(TENANT_OWNED_TABLES):
        if table_name not in existing_tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            continue
        index_name = f"ix_{table_name}_tenant_id"
        if index_name in _index_names(inspector, table_name):
            op.drop_index(index_name, table_name=table_name)
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("tenant_id")
        inspector = sa.inspect(bind)

    Base.metadata.tables["tenants"].drop(bind=bind, checkfirst=True)
