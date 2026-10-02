"""Tabla de referencia de instrumentos (ticker/FIGI/ISIN/sector)."""
import sqlalchemy as sa

from alembic import op

revision = "0047_instrument_references"
down_revision = "0046_inferred_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker_normalized", sa.String(length=40), nullable=False),
        sa.Column("figi", sa.String(length=12), nullable=True),
        sa.Column("composite_figi", sa.String(length=12), nullable=True),
        sa.Column("shareclass_figi", sa.String(length=12), nullable=True),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("cusip", sa.String(length=9), nullable=True),
        sa.Column("sedol", sa.String(length=7), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("exchange", sa.String(length=20), nullable=True),
        sa.Column("mic", sa.String(length=4), nullable=True),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column("industry", sa.String(length=160), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="financedatabase"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ticker_normalized", name="uq_instrument_ref_ticker"),
    )
    op.create_index(
        "ix_instrument_ref_ticker", "instrument_references", ["ticker_normalized"]
    )
    op.create_index("ix_instrument_ref_figi", "instrument_references", ["figi"])
    op.create_index(
        "ix_instrument_ref_composite_figi", "instrument_references", ["composite_figi"]
    )
    op.create_index("ix_instrument_ref_isin", "instrument_references", ["isin"])


def downgrade() -> None:
    op.drop_index("ix_instrument_ref_isin", table_name="instrument_references")
    op.drop_index("ix_instrument_ref_composite_figi", table_name="instrument_references")
    op.drop_index("ix_instrument_ref_figi", table_name="instrument_references")
    op.drop_index("ix_instrument_ref_ticker", table_name="instrument_references")
    op.drop_table("instrument_references")
