"""Candidatos INFERIDOS de empresa por tema de cuello de botella."""
import sqlalchemy as sa

from alembic import op

revision = "0057_bottleneck_discovery"
down_revision = "0056_bottleneck_signal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bottleneck_discovery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("theme", sa.String(80), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("n_sources", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "theme", "ticker", "day", name="uq_bottleneck_discovery_day"),
        sa.CheckConstraint("label = 'INFERIDO'", name="ck_bottleneck_discovery_label"),
    )
    op.create_index("ix_bottleneck_discovery_tenant_id", "bottleneck_discovery", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_bottleneck_discovery_tenant_id", table_name="bottleneck_discovery")
    op.drop_table("bottleneck_discovery")
