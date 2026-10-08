"""Explicit opt-in for outgoing Telegram alerts; existing users stay silent."""
import sqlalchemy as sa

from alembic import op

revision = "0051_alert_subscriptions"
down_revision = "0050_thesis_backtest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("chat_id", sa.String(32), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_type", name="uq_alert_subscription_type"),
    )
    op.create_index("ix_alert_subscriptions_tenant_id", "alert_subscriptions", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("alert_subscriptions")
