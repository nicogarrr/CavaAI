"""provider-specific LLM model aliases

Revision ID: 0011_model_aliases
Revises: 0010_alert_rules
Create Date: 2026-07-16 00:00:00
"""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0011_model_aliases"
down_revision = "0010_alert_rules"
branch_labels = None
depends_on = None


MODEL_ALIASES = (
    (
        "qwen-flash", "qwen/qwen3.6-flash", 1_000_000, "0.1875", "1.125",
        ["text", "image", "video", "reasoning", "tool_calling", "structured_output"],
    ),
    (
        "qwen3.7-plus", "qwen/qwen3.7-plus", 1_000_000, "0.32", "1.28",
        ["text", "image", "reasoning", "tool_calling", "structured_output"],
    ),
    (
        "glm-5.2", "z-ai/glm-5.2", 1_048_576, "0.9702", "3.0492",
        ["text", "reasoning", "tool_calling", "structured_output"],
    ),
    (
        "qwen3.7-max", "qwen/qwen3.7-max", 1_000_000, "1.475", "4.425",
        ["text", "reasoning", "tool_calling", "structured_output"],
    ),
    (
        "kimi-k2.7-code", "moonshotai/kimi-k2.7-code", 262_144, "0.719", "3.49",
        ["text", "image", "reasoning", "tool_calling", "structured_output"],
    ),
    (
        "deepseek-v4-flash", "deepseek/deepseek-v4-flash", 1_048_575, "0.098", "0.196",
        ["text", "reasoning", "tool_calling", "structured_output"],
    ),
)


def upgrade() -> None:
    table = op.create_table(
        "model_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("internal_alias", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_model_id", sa.String(240), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("input_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("output_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("supported_capabilities", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("internal_alias", "provider", name="uq_model_alias_provider"),
    )
    op.create_index("ix_model_aliases_internal_alias", "model_aliases", ["internal_alias"])
    op.create_index("ix_model_aliases_provider", "model_aliases", ["provider"])
    op.create_index("ix_model_aliases_enabled", "model_aliases", ["enabled"])

    now = datetime.now(UTC)
    op.bulk_insert(
        table,
        [
            {
                "internal_alias": alias,
                "provider": "openrouter",
                "provider_model_id": model_id,
                "enabled": True,
                "context_window": context_window,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "supported_capabilities": capabilities,
                "created_at": now,
                "updated_at": now,
            }
            for alias, model_id, context_window, input_cost, output_cost, capabilities
            in MODEL_ALIASES
        ],
    )


def downgrade() -> None:
    op.drop_table("model_aliases")
