"""0037 dated market observations and snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "0037_market_observations"
down_revision = "0036_alert_last_triggered_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("geography", sa.String(80), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit", sa.String(80), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("vintage", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "metric_key",
            "geography",
            "observation_date",
            "source",
            "vintage",
            name="uq_market_observation_vintage",
        ),
    )
    op.create_index(
        "ix_market_observations_metric_date", "market_observations", ["metric_key", "observation_date"]
    )
    op.create_table(
        "market_regime_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.String(40), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("snapshot_date", "model_version", "input_hash", name="uq_market_regime_inputs"),
    )
    op.create_index("ix_market_regime_snapshots_snapshot_date", "market_regime_snapshots", ["snapshot_date"])


def downgrade() -> None:
    op.drop_table("market_regime_snapshots")
    op.drop_table("market_observations")
