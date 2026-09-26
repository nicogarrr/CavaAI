"""tax reports, investment plans, plan contributions and corporate actions

Revision ID: 0018_personal_finance_modules
Revises: 0017_opencode_go_model_alias
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_personal_finance_modules"
down_revision = "0017_opencode_go_model_alias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=True, index=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, index=True),
        sa.Column("base_currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("dividends", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("realized", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("misc", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "fiscal_year", name="uq_tax_report_tenant_year"),
    )

    op.create_table(
        "investment_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=True, index=True),
        sa.Column("monthly_contribution", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("horizon_years", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("target_allocations", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(40), nullable=False, server_default="active", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "plan_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("investment_plans.id"), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("external_id", sa.String(120), nullable=True),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "plan_id", "external_id", name="uq_plan_contribution_tenant_external"),
    )

    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("action_type", sa.String(40), nullable=False, server_default="split", index=True),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("ratio", sa.Numeric(24, 10), nullable=False, server_default="1"),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_corporate_actions_tenant_id", table_name="corporate_actions")
    op.drop_table("corporate_actions")
    op.drop_index("ix_plan_contributions_tenant_id", table_name="plan_contributions")
    op.drop_table("plan_contributions")
    op.drop_index("ix_investment_plans_tenant_id", table_name="investment_plans")
    op.drop_table("investment_plans")
    op.drop_index("ix_tax_reports_tenant_id", table_name="tax_reports")
    op.drop_table("tax_reports")
