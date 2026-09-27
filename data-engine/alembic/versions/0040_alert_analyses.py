"""Persist versioned, tenant-scoped news alert analyses."""

import sqlalchemy as sa

from alembic import op

revision = "0040_alert_analyses"
down_revision = "0039_primary_source_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("alert_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id")),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("research_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("news_event_id", sa.Integer(), sa.ForeignKey("news_events.id"), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "alert_id", "version", name="uq_alert_analysis_version"))
    for name in ("tenant_id", "alert_id", "news_event_id"):
        op.create_index(f"ix_alert_analyses_{name}", "alert_analyses", [name])


def downgrade() -> None:
    op.drop_table("alert_analyses")
