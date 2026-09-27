"""Unassigned ITU registry notices, first-seen separately from BR date."""

import sqlalchemy as sa

from alembic import op

revision = "0041_itu_notices"
down_revision = "0040_alert_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("itu_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id")),
        sa.Column("submission_id", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("notice_id", sa.String(40), nullable=False),
        sa.Column("satellite_name", sa.String(500), nullable=False),
        sa.Column("br_registry_date", sa.String(20), nullable=False),
        sa.Column("submission_type", sa.String(120), nullable=False),
        sa.Column("act_code", sa.String(10), nullable=False),
        sa.Column("detail_url", sa.String(1000), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "submission_id", name="uq_itu_notice_submission"))
    op.create_index("ix_itu_notices_tenant_id", "itu_notices", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("itu_notices")
