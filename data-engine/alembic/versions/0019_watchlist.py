"""research watchlist (tenant-scoped symbols)

Revision ID: 0019_watchlist
Revises: 0018_personal_finance_modules
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_watchlist"
down_revision = "0018_personal_finance_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "symbol", name="uq_watch_item_tenant_symbol"),
    )


def downgrade() -> None:
    op.drop_index("ix_watch_items_tenant_id", table_name="watch_items")
    op.drop_index("ix_watch_items_symbol", table_name="watch_items")
    op.drop_table("watch_items")