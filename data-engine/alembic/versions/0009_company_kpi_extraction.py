"""company-specific KPI registry and approval pipeline

Revision ID: 0009_company_kpi_extraction
Revises: 0008_financial_model_v2
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_company_kpi_extraction"
down_revision = "0008_financial_model_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_kpis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("canonical_unit", sa.String(40), nullable=False),
        sa.Column("period_type", sa.String(40), nullable=False),
        sa.Column("driver_type", sa.String(60), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("registry_version", sa.String(80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "metric_key", name="uq_company_kpi_metric"),
    )
    for column in ("company_id", "metric_key", "active", "tenant_id"):
        op.create_index(f"ix_company_kpis_{column}", "company_kpis", [column])

    op.create_table(
        "kpi_extraction_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("company_kpi_id", sa.Integer(), sa.ForeignKey("company_kpis.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("raw_label", sa.String(240), nullable=False),
        sa.Column("raw_value", sa.String(160), nullable=False),
        sa.Column("raw_unit", sa.String(80), nullable=False),
        sa.Column("normalized_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("canonical_unit", sa.String(40), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column("reconciliation_status", sa.String(60), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("extraction_model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canonical_fact_id", sa.Integer(), sa.ForeignKey("financial_facts.id"), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "document_chunk_id", "metric_key", "period", "raw_value",
            name="uq_kpi_candidate_observation",
        ),
    )
    for column in (
        "company_id", "company_kpi_id", "document_id", "document_chunk_id",
        "metric_key", "period", "fiscal_year", "status", "canonical_fact_id", "tenant_id",
    ):
        op.create_index(
            f"ix_kpi_extraction_candidates_{column}",
            "kpi_extraction_candidates",
            [column],
        )


def downgrade() -> None:
    op.drop_table("kpi_extraction_candidates")
    op.drop_table("company_kpis")
