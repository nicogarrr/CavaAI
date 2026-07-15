"""persisted fundamental model, decision journal and expectation reviews

Revision ID: 0006_fundamental_model_journal
Revises: 0005_tenant_document_chunks
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_fundamental_model_journal"
down_revision = "0005_tenant_document_chunks"
branch_labels = None
depends_on = None


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "fundamental_model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(160), nullable=False),
        sa.Column("framework_key", sa.String(80), nullable=False),
        sa.Column("horizon_years", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("scenario_probabilities", sa.JSON(), nullable=False),
        sa.Column("model_snapshot", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "version", name="uq_fundamental_model_tenant_version"),
        sa.UniqueConstraint("tenant_id", "company_id", "input_fingerprint", name="uq_fundamental_model_fingerprint"),
    )
    op.create_index("ix_fundamental_model_versions_tenant_id", "fundamental_model_versions", ["tenant_id"])
    op.create_index("ix_fundamental_model_versions_company_id", "fundamental_model_versions", ["company_id"])
    op.create_index("ix_fundamental_model_versions_framework_key", "fundamental_model_versions", ["framework_key"])
    op.create_index("ix_fundamental_model_versions_status", "fundamental_model_versions", ["status"])
    op.create_index("ix_fundamental_model_versions_input_fingerprint", "fundamental_model_versions", ["input_fingerprint"])

    op.create_table(
        "fundamental_drivers",
        sa.Column("id", sa.Integer(), primary_key=True), *_tenant_columns(),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("driver_key", sa.String(160), nullable=False), sa.Column("driver_type", sa.String(40), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False), sa.Column("status", sa.String(40), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=True), sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False), sa.Column("source_fact_ids", sa.JSON(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "model_version_id", "driver_key", name="uq_fundamental_driver_version_key"),
    )
    op.create_index("ix_fundamental_drivers_tenant_id", "fundamental_drivers", ["tenant_id"])
    op.create_index("ix_fundamental_drivers_model_version_id", "fundamental_drivers", ["model_version_id"])
    op.create_index("ix_fundamental_drivers_company_id", "fundamental_drivers", ["company_id"])
    op.create_index("ix_fundamental_drivers_driver_key", "fundamental_drivers", ["driver_key"])
    op.create_index("ix_fundamental_drivers_status", "fundamental_drivers", ["status"])

    op.create_table(
        "fundamental_assumptions",
        sa.Column("id", sa.Integer(), primary_key=True), *_tenant_columns(),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("assumption_key", sa.String(160), nullable=False), sa.Column("scenario", sa.String(40), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=True), sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False), sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False), sa.Column("source_fact_ids", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "model_version_id", "scenario", "assumption_key", name="uq_fundamental_assumption_version_scenario_key"),
    )
    op.create_index("ix_fundamental_assumptions_tenant_id", "fundamental_assumptions", ["tenant_id"])
    op.create_index("ix_fundamental_assumptions_model_version_id", "fundamental_assumptions", ["model_version_id"])
    op.create_index("ix_fundamental_assumptions_company_id", "fundamental_assumptions", ["company_id"])
    op.create_index("ix_fundamental_assumptions_assumption_key", "fundamental_assumptions", ["assumption_key"])

    op.create_table(
        "fundamental_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True), *_tenant_columns(),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("scenario", sa.String(40), nullable=False), sa.Column("probability", sa.Numeric(7, 6), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False), sa.Column("metric", sa.String(160), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False), sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("source_fact_ids", sa.JSON(), nullable=False), sa.Column("trace", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "model_version_id", "scenario", "fiscal_year", "metric", name="uq_fundamental_forecast_point"),
    )
    for name, cols in (("tenant_id", ["tenant_id"]), ("model_version_id", ["model_version_id"]), ("company_id", ["company_id"]), ("scenario", ["scenario"]), ("fiscal_year", ["fiscal_year"]), ("metric", ["metric"])):
        op.create_index(f"ix_fundamental_forecasts_{name}", "fundamental_forecasts", cols)

    op.create_table(
        "decision_journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True), *_tenant_columns(),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False), sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False), sa.Column("what_must_be_true", sa.JSON(), nullable=False),
        sa.Column("price", sa.Numeric(20, 4), nullable=True), sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    for name in ("tenant_id", "company_id", "thesis_version_id", "model_version_id", "decision", "status"):
        op.create_index(f"ix_decision_journal_entries_{name}", "decision_journal_entries", [name])

    op.create_table(
        "expectation_reviews",
        sa.Column("id", sa.Integer(), primary_key=True), *_tenant_columns(),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=False),
        sa.Column("forecast_id", sa.Integer(), sa.ForeignKey("fundamental_forecasts.id"), nullable=False),
        sa.Column("actual_fact_id", sa.Integer(), sa.ForeignKey("financial_facts.id"), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False), sa.Column("metric", sa.String(160), nullable=False),
        sa.Column("expected_value", sa.Numeric(24, 8), nullable=False), sa.Column("actual_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("variance", sa.Numeric(24, 8), nullable=True), sa.Column("variance_percent", sa.Numeric(12, 8), nullable=True),
        sa.Column("status", sa.String(40), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "forecast_id", name="uq_expectation_review_forecast"),
    )
    for name in ("tenant_id", "company_id", "model_version_id", "forecast_id", "actual_fact_id", "fiscal_year", "metric", "status"):
        op.create_index(f"ix_expectation_reviews_{name}", "expectation_reviews", [name])


def downgrade() -> None:
    op.drop_table("expectation_reviews")
    op.drop_table("decision_journal_entries")
    op.drop_table("fundamental_forecasts")
    op.drop_table("fundamental_assumptions")
    op.drop_table("fundamental_drivers")
    op.drop_table("fundamental_model_versions")
