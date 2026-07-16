"""principle jobs, lineage and historical portfolio snapshots

Revision ID: 0016_principle_jobs_snapshots
Revises: 0015_management_promises
Create Date: 2026-07-16 00:00:00
"""

from alembic import op
import hashlib
import sqlalchemy as sa


revision = "0016_principle_jobs_snapshots"
down_revision = "0015_management_promises"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True)


def upgrade() -> None:
    with op.batch_alter_table("investment_principles") as batch:
        batch.add_column(sa.Column("principle_fingerprint", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "semantic_duplicate_of_id",
                sa.Integer(),
                sa.ForeignKey("investment_principles.id"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "canonical_principle_id",
                sa.Integer(),
                sa.ForeignKey("investment_principles.id"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "superseded_by_id",
                sa.Integer(),
                sa.ForeignKey("investment_principles.id"),
                nullable=True,
            )
        )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, principle FROM investment_principles "
            "WHERE principle_fingerprint IS NULL"
        )
    ).mappings()
    for row in rows:
        fingerprint = hashlib.sha256(str(row["principle"]).strip().lower().encode()).hexdigest()
        connection.execute(
            sa.text(
                "UPDATE investment_principles SET principle_fingerprint = :fingerprint "
                "WHERE id = :principle_id"
            ),
            {"fingerprint": fingerprint, "principle_id": row["id"]},
        )
    with op.batch_alter_table("investment_principles") as batch:
        batch.alter_column("principle_fingerprint", nullable=False)
    for column in (
        "principle_fingerprint",
        "semantic_duplicate_of_id",
        "canonical_principle_id",
        "superseded_by_id",
    ):
        op.create_index(
            f"ix_investment_principles_{column}", "investment_principles", [column]
        )

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _tenant(),
        *_timestamps(),
    )
    for column in ("job_type", "entity_type", "entity_id", "status", "tenant_id"):
        op.create_index(f"ix_processing_jobs_{column}", "processing_jobs", [column])

    op.create_table(
        "portfolio_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(10), nullable=False),
        sa.Column("positions_value_base", sa.Numeric(24, 6), nullable=False),
        sa.Column("cash_value_base", sa.Numeric(24, 6), nullable=False),
        sa.Column("total_value_base", sa.Numeric(24, 6), nullable=False),
        sa.Column("net_external_flow_base", sa.Numeric(24, 6), nullable=False),
        sa.Column("daily_return", sa.Numeric(18, 10), nullable=True),
        sa.Column("cumulative_twr", sa.Numeric(18, 10), nullable=True),
        sa.Column("pricing_coverage", sa.Numeric(5, 4), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_id",
            "snapshot_date",
            name="uq_portfolio_daily_snapshot_tenant_date",
        ),
    )
    for column in ("portfolio_id", "snapshot_date", "tenant_id"):
        op.create_index(
            f"ix_portfolio_daily_snapshots_{column}",
            "portfolio_daily_snapshots",
            [column],
        )

    op.create_table(
        "position_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_daily_snapshots.id"),
            nullable=False,
        ),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("market_price_native", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("fx_rate", sa.Numeric(20, 10), nullable=True),
        sa.Column("market_value_native", sa.Numeric(24, 6), nullable=False),
        sa.Column("market_value_base", sa.Numeric(24, 6), nullable=True),
        sa.Column("weight", sa.Numeric(18, 10), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "portfolio_snapshot_id",
            "company_id",
            name="uq_position_daily_snapshot_company",
        ),
    )
    for column in (
        "portfolio_snapshot_id",
        "portfolio_id",
        "company_id",
        "snapshot_date",
        "tenant_id",
    ):
        op.create_index(
            f"ix_position_daily_snapshots_{column}",
            "position_daily_snapshots",
            [column],
        )

    op.create_table(
        "cash_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_daily_snapshots.id"),
            nullable=False,
        ),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("balance_native", sa.Numeric(24, 6), nullable=False),
        sa.Column("fx_rate", sa.Numeric(20, 10), nullable=True),
        sa.Column("balance_base", sa.Numeric(24, 6), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "portfolio_snapshot_id",
            "currency",
            name="uq_cash_daily_snapshot_currency",
        ),
    )
    for column in (
        "portfolio_snapshot_id",
        "portfolio_id",
        "snapshot_date",
        "currency",
        "tenant_id",
    ):
        op.create_index(
            f"ix_cash_daily_snapshots_{column}",
            "cash_daily_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("cash_daily_snapshots")
    op.drop_table("position_daily_snapshots")
    op.drop_table("portfolio_daily_snapshots")
    op.drop_table("processing_jobs")
    for column in (
        "superseded_by_id",
        "canonical_principle_id",
        "semantic_duplicate_of_id",
        "principle_fingerprint",
    ):
        op.drop_index(
            f"ix_investment_principles_{column}",
            table_name="investment_principles",
        )
    with op.batch_alter_table("investment_principles") as batch:
        for column in (
            "superseded_by_id",
            "version",
            "canonical_principle_id",
            "semantic_duplicate_of_id",
            "principle_fingerprint",
        ):
            batch.drop_column(column)
