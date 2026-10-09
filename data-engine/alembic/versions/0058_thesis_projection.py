"""Proyecciones anuales de tesis a 5 ejercicios por escenario (aditiva)."""
import sqlalchemy as sa

from alembic import op

revision = "0058_thesis_projection"
down_revision = "0057_bottleneck_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_projection_years",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "valuation_model_id",
            sa.Integer(),
            sa.ForeignKey("valuation_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("scenario", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(24, 6), nullable=True),
        sa.Column("fcf", sa.Numeric(24, 6), nullable=True),
        sa.Column("eps", sa.Numeric(24, 8), nullable=True),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "scenario",
            "fiscal_year",
            "day",
            name="uq_thesis_projection_year_day",
        ),
        sa.CheckConstraint(
            "label IN ('INFERIDO', 'N/D')", name="ck_thesis_projection_year_label"
        ),
    )
    op.create_index(
        "ix_thesis_projection_years_company",
        "thesis_projection_years",
        ["company_id", "scenario", "fiscal_year"],
    )
    op.create_index(
        "ix_thesis_projection_years_tenant_id", "thesis_projection_years", ["tenant_id"]
    )
    op.create_index(
        "ix_thesis_projection_years_valuation_model_id",
        "thesis_projection_years",
        ["valuation_model_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thesis_projection_years_valuation_model_id",
        table_name="thesis_projection_years",
    )
    op.drop_index(
        "ix_thesis_projection_years_tenant_id", table_name="thesis_projection_years"
    )
    op.drop_index(
        "ix_thesis_projection_years_company", table_name="thesis_projection_years"
    )
    op.drop_table("thesis_projection_years")
