"""financial model reproducibility, valuation snapshots and metric semantics

Revision ID: 0008_financial_model_v2
Revises: 0007_portfolio_fx_snapshot_v2
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_financial_model_v2"
down_revision = "0007_portfolio_fx_snapshot_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fundamental_model_versions") as batch:
        batch.add_column(sa.Column("algorithm_version", sa.String(160), nullable=True))
        batch.add_column(sa.Column("forecast_fingerprint", sa.String(64), nullable=True))
        batch.add_column(sa.Column("market_snapshot_fingerprint", sa.String(64), nullable=True))
        batch.add_column(sa.Column("valuation_snapshot_fingerprint", sa.String(64), nullable=True))
        batch.add_column(sa.Column("code_commit_sha", sa.String(80), nullable=False, server_default="unknown"))
    op.execute(
        sa.text(
            "UPDATE fundamental_model_versions SET "
            "algorithm_version = engine_version, "
            "forecast_fingerprint = input_fingerprint, "
            "market_snapshot_fingerprint = input_fingerprint, "
            "valuation_snapshot_fingerprint = input_fingerprint"
        )
    )
    with op.batch_alter_table("fundamental_model_versions") as batch:
        for column in (
            "algorithm_version", "forecast_fingerprint",
            "market_snapshot_fingerprint", "valuation_snapshot_fingerprint",
        ):
            batch.alter_column(column, nullable=False)
            batch.create_index(f"ix_fundamental_model_versions_{column}", [column])

    op.create_table(
        "fundamental_valuation_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("fundamental_model_versions.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("current_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("market_snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("valuation_snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "model_version_id", "market_snapshot_fingerprint",
            name="uq_fundamental_valuation_market_snapshot",
        ),
    )
    for column in (
        "tenant_id", "model_version_id", "company_id",
        "market_snapshot_fingerprint", "valuation_snapshot_fingerprint",
    ):
        op.create_index(f"ix_fundamental_valuation_snapshots_{column}", "fundamental_valuation_snapshots", [column])

    with op.batch_alter_table("expectation_reviews") as batch:
        batch.add_column(sa.Column("actual_metric_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("actual_source_type", sa.String(40), nullable=True))
        batch.add_column(sa.Column("semantics", sa.String(40), nullable=False, server_default="higher_is_better"))
        batch.create_foreign_key("fk_expectation_review_actual_metric", "calculated_metrics", ["actual_metric_id"], ["id"])
        batch.create_index("ix_expectation_reviews_actual_metric_id", ["actual_metric_id"])

    with op.batch_alter_table("thesis_versions") as batch:
        for column in (
            "current_price", "bear_value", "base_value", "bull_value",
            "expected_value", "margin_of_safety",
        ):
            batch.alter_column(column, nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("thesis_versions") as batch:
        for column in (
            "current_price", "bear_value", "base_value", "bull_value",
            "expected_value", "margin_of_safety",
        ):
            batch.alter_column(column, nullable=False, server_default="0")
    with op.batch_alter_table("expectation_reviews") as batch:
        batch.drop_index("ix_expectation_reviews_actual_metric_id")
        batch.drop_constraint("fk_expectation_review_actual_metric", type_="foreignkey")
        batch.drop_column("semantics")
        batch.drop_column("actual_source_type")
        batch.drop_column("actual_metric_id")
    op.drop_table("fundamental_valuation_snapshots")
    with op.batch_alter_table("fundamental_model_versions") as batch:
        for column in (
            "valuation_snapshot_fingerprint", "market_snapshot_fingerprint",
            "forecast_fingerprint", "algorithm_version",
        ):
            batch.drop_index(f"ix_fundamental_model_versions_{column}")
            batch.drop_column(column)
        batch.drop_column("code_commit_sha")
