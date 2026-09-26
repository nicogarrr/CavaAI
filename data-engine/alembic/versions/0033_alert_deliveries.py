"""0033 alert deliveries outbox

Per-channel delivery rows for research alerts with an atomic claim. One row
per (alert, channel); dispatch claims with a single UPDATE ... WHERE status
eligible RETURNING, so two workers cannot send the same channel at once and
a commit that fails right after a send leaves the row in 'sending', which an
immediate retry will not reclaim. Stale claims become eligible again after
the service-level TTL (residual at-least-once, documented in the service).
"""

import sqlalchemy as sa

from alembic import op

revision = "0033_alert_deliveries"
down_revision = "0032_tenant_uniques_fk_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("research_alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("alert_id", "channel", name="uq_alert_delivery_channel"),
    )
    op.create_index("ix_alert_deliveries_alert_id", "alert_deliveries", ["alert_id"])
    op.create_index("ix_alert_deliveries_status", "alert_deliveries", ["status"])
    op.create_index("ix_alert_deliveries_tenant_id", "alert_deliveries", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_deliveries_tenant_id", table_name="alert_deliveries")
    op.drop_index("ix_alert_deliveries_status", table_name="alert_deliveries")
    op.drop_index("ix_alert_deliveries_alert_id", table_name="alert_deliveries")
    op.drop_table("alert_deliveries")
