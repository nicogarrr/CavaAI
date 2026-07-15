"""persistent evaluated alert rules

Revision ID: 0010_alert_rules
Revises: 0009_company_kpi_extraction
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_alert_rules"
down_revision = "0009_company_kpi_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("rule_type", sa.String(80), nullable=False),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("target", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.String(160), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "company_id", "name", name="uq_alert_rule_name"),
    )
    for column in ("company_id", "rule_type", "active", "tenant_id"):
        op.create_index(f"ix_alert_rules_{column}", "alert_rules", [column])


def downgrade() -> None:
    op.drop_table("alert_rules")
