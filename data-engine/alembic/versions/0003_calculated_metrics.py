"""calculated metrics table

Revision ID: 0003_calculated_metrics
Revises: 0002_research_memory
Create Date: 2026-07-09 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_calculated_metrics"
down_revision = "0002_research_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculated_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("metric", sa.String(120), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=True),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("numerator", sa.Numeric(24, 8), nullable=True),
        sa.Column("denominator", sa.Numeric(24, 8), nullable=True),
        sa.Column("source_fact_ids", sa.JSON(), nullable=False),
        sa.Column("calculation_trace", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "metric", "period", "definition_version", name="uq_calculated_metric_definition_period"),
    )
    op.create_index("ix_calculated_metrics_company_id", "calculated_metrics", ["company_id"], unique=False)
    op.create_index("ix_calculated_metrics_metric", "calculated_metrics", ["metric"], unique=False)
    op.create_index("ix_calculated_metrics_period", "calculated_metrics", ["period"], unique=False)
    op.create_index("ix_calculated_metrics_tenant_id", "calculated_metrics", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("calculated_metrics")
