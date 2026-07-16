"""custom metrics and persistent screener

Revision ID: 0013_screener_engine
Revises: 0012_knowledge_integrity
Create Date: 2026-07-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_screener_engine"
down_revision = "0012_knowledge_integrity"
branch_labels = None
depends_on = None


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "custom_metric_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("metric_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "metric_key", "version", name="uq_custom_metric_key_version"
        ),
    )
    for column in ("metric_key", "active", "tenant_id"):
        op.create_index(
            f"ix_custom_metric_definitions_{column}",
            "custom_metric_definitions",
            [column],
        )

    op.create_table(
        "saved_screens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("ranking_formula", sa.Text(), nullable=True),
        sa.Column("ranking_direction", sa.String(10), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_saved_screen_tenant_name"),
    )
    for column in ("alerts_enabled", "active", "tenant_id"):
        op.create_index(f"ix_saved_screens_{column}", "saved_screens", [column])

    op.create_table(
        "saved_screen_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "saved_screen_id",
            sa.Integer(),
            sa.ForeignKey("saved_screens.id"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("first_matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "saved_screen_id", "company_id", name="uq_screen_match_company"
        ),
    )
    for column in ("saved_screen_id", "company_id", "active", "tenant_id"):
        op.create_index(
            f"ix_saved_screen_matches_{column}", "saved_screen_matches", [column]
        )


def downgrade() -> None:
    op.drop_table("saved_screen_matches")
    op.drop_table("saved_screens")
    op.drop_table("custom_metric_definitions")
