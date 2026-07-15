"""portfolio base currency and historical FX accounting

Revision ID: 0007_portfolio_fx_snapshot_v2
Revises: 0006_fundamental_model_journal
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_portfolio_fx_snapshot_v2"
down_revision = "0006_fundamental_model_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False, server_default="Main"),
        sa.Column("base_currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_portfolio_tenant_name"),
    )
    op.create_index("ix_portfolios_tenant_id", "portfolios", ["tenant_id"])
    op.create_index("ix_portfolios_is_default", "portfolios", ["is_default"])

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("base_currency", sa.String(10), nullable=False),
        sa.Column("quote_currency", sa.String(10), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "base_currency", "quote_currency", "rate_date",
            name="uq_fx_rate_tenant_pair_date",
        ),
    )
    for column in ("tenant_id", "base_currency", "quote_currency", "rate_date"):
        op.create_index(f"ix_fx_rates_{column}", "fx_rates", [column])

    with op.batch_alter_table("positions") as batch:
        batch.add_column(sa.Column("portfolio_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("base_currency", sa.String(10), nullable=False, server_default="EUR"))
        batch.add_column(sa.Column("market_value_native", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("market_value_base", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("cost_basis_native", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("cost_basis_base", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("unrealized_pnl_base", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("realized_pnl_base", sa.Numeric(24, 6), nullable=True))
        batch.add_column(sa.Column("fx_rate", sa.Numeric(20, 10), nullable=True))
        batch.create_foreign_key("fk_positions_portfolio_id", "portfolios", ["portfolio_id"], ["id"])
        batch.create_index("ix_positions_portfolio_id", ["portfolio_id"])

    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("portfolio_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_transactions_portfolio_id", "portfolios", ["portfolio_id"], ["id"])
        batch.create_index("ix_transactions_portfolio_id", ["portfolio_id"])

    op.execute(
        sa.text(
            "UPDATE positions SET market_value_native = market_value, "
            "cost_basis_native = quantity * average_cost"
        )
    )
    op.execute(
        sa.text(
            "UPDATE positions SET market_value_base = market_value_native, "
            "cost_basis_base = cost_basis_native, "
            "unrealized_pnl_base = unrealized_pnl, realized_pnl_base = realized_pnl, "
            "fx_rate = 1 WHERE currency = 'EUR'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_index("ix_transactions_portfolio_id")
        batch.drop_constraint("fk_transactions_portfolio_id", type_="foreignkey")
        batch.drop_column("portfolio_id")
    with op.batch_alter_table("positions") as batch:
        batch.drop_index("ix_positions_portfolio_id")
        batch.drop_constraint("fk_positions_portfolio_id", type_="foreignkey")
        for column in (
            "fx_rate", "realized_pnl_base", "unrealized_pnl_base",
            "cost_basis_base", "cost_basis_native", "market_value_base",
            "market_value_native", "base_currency", "portfolio_id",
        ):
            batch.drop_column(column)
    op.drop_table("fx_rates")
    op.drop_table("portfolios")
