"""management credibility promises

Revision ID: 0015_management_promises
Revises: 0014_decision_learning_graph
Create Date: 2026-07-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_management_promises"
down_revision = "0014_decision_learning_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_promises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("call_claim_id", sa.Integer(), sa.ForeignKey("call_claims.id"), nullable=True, unique=True),
        sa.Column("promise", sa.Text(), nullable=False),
        sa.Column("promise_date", sa.Date(), nullable=False),
        sa.Column("expected_period", sa.String(80), nullable=False),
        sa.Column("metric", sa.String(160), nullable=True),
        sa.Column("operator", sa.String(10), nullable=True),
        sa.Column("target_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("actual_fact_id", sa.Integer(), sa.ForeignKey("financial_facts.id"), nullable=True),
        sa.Column("actual_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("management_explanation", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "company_id",
        "source_document_id",
        "call_claim_id",
        "promise_date",
        "expected_period",
        "metric",
        "actual_fact_id",
        "status",
        "tenant_id",
    ):
        op.create_index(
            f"ix_management_promises_{column}", "management_promises", [column]
        )


def downgrade() -> None:
    op.drop_table("management_promises")
