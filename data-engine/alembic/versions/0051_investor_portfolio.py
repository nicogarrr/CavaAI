"""Carteras de inversores publicos: posiciones y movimientos con etiqueta y fecha."""
import sqlalchemy as sa

from alembic import op

revision = "0051_investor_portfolio"
down_revision = "0050_thesis_backtest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investor_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("investor_slug", sa.String(60), nullable=False),
        sa.Column("issuer_name", sa.String(200), nullable=False),
        sa.Column("issuer_cik", sa.String(10), nullable=False, server_default=""),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("security_title", sa.String(150), nullable=False, server_default=""),
        sa.Column("shares", sa.Numeric(24, 4), nullable=True),
        sa.Column("ownership_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("value_usd", sa.Numeric(24, 2), nullable=True),
        sa.Column("label", sa.String(12), nullable=False, server_default="OFICIAL"),
        sa.Column("value_label", sa.String(12), nullable=False, server_default="SIN_DATOS"),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source_form", sa.String(20), nullable=False, server_default=""),
        sa.Column("accession_number", sa.String(25), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "investor_slug", "issuer_cik", "security_title", "as_of",
            name="uq_investor_position",
        ),
    )
    op.create_index("ix_investor_positions_tenant_id", "investor_positions", ["tenant_id"])
    op.create_index("ix_investor_positions_investor_slug", "investor_positions", ["investor_slug"])

    op.create_table(
        "investor_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("investor_slug", sa.String(60), nullable=False),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issuer_name", sa.String(200), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("action", sa.String(20), nullable=False, server_default="otro"),
        sa.Column("transaction_code", sa.String(4), nullable=False, server_default=""),
        sa.Column("shares", sa.Numeric(24, 4), nullable=True),
        sa.Column("price_usd", sa.Numeric(20, 6), nullable=True),
        sa.Column("shares_after", sa.Numeric(24, 4), nullable=True),
        sa.Column("label", sa.String(12), nullable=False, server_default="OFICIAL"),
        sa.Column("source_form", sa.String(20), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "investor_slug", "accession_number", "line_no",
            name="uq_investor_movement",
        ),
    )
    op.create_index("ix_investor_movements_tenant_id", "investor_movements", ["tenant_id"])
    op.create_index("ix_investor_movements_investor_slug", "investor_movements", ["investor_slug"])
    op.create_index("ix_investor_movements_movement_date", "investor_movements", ["movement_date"])


def downgrade() -> None:
    op.drop_table("investor_movements")
    op.drop_table("investor_positions")
