"""Inputs INFERIDO con base explicita y URLs (relajacion acotada de #691)."""
import sqlalchemy as sa

from alembic import op

revision = "0046_inferred_inputs"
down_revision = "0045_thesis_valuation_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inferred_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("input_key", sa.String(80), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False, server_default="decimal"),
        sa.Column("base", sa.Text(), nullable=False),
        sa.Column("source_urls", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False, server_default="llm"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_inferred_inputs_tenant_id", "inferred_inputs", ["tenant_id"])
    op.create_index("ix_inferred_inputs_company_id", "inferred_inputs", ["company_id"])
    op.create_index(
        "ix_inferred_inputs_company_key", "inferred_inputs", ["company_id", "input_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_inferred_inputs_company_key", table_name="inferred_inputs")
    op.drop_index("ix_inferred_inputs_company_id", table_name="inferred_inputs")
    op.drop_index("ix_inferred_inputs_tenant_id", table_name="inferred_inputs")
    op.drop_table("inferred_inputs")
