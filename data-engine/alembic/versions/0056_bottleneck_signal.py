"""Deterministic supply constraints from already-ingested evidence."""
import sqlalchemy as sa

from alembic import op

revision = "0056_bottleneck_signal"
down_revision = "0055_telegram_chat_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bottleneck_signal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("theme", sa.String(80), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True)),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("n_sources", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "theme", name="uq_bottleneck_tenant_theme"),
    )
    op.create_index("ix_bottleneck_signal_tenant_id", "bottleneck_signal", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_bottleneck_signal_tenant_id", table_name="bottleneck_signal")
    op.drop_table("bottleneck_signal")
