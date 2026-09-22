"""0024 workflow run envelope

Uniform run/step execution envelope: workflow_runs records every workflow
execution (state machine, idempotency key, classified error) and
workflow_step_runs records each executed step. Basis for truthful run
status, idempotent re-delivery and later replay/crash-resume validation.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_workflow_run_envelope"
down_revision = "0023_insider_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("workflow_name", sa.String(120), nullable=False),
        sa.Column("execution_mode", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_class", sa.String(120), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "workflow_name", "idempotency_key",
            name="uq_workflow_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_workflow_runs_name_status", "workflow_runs", ["workflow_name", "status"]
    )
    op.create_index("ix_workflow_runs_tenant_id", "workflow_runs", ["tenant_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_class", sa.String(120), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "run_id", "position", "attempt", name="uq_workflow_step_runs_position_attempt"
        ),
    )
    op.create_index("ix_workflow_step_runs_run", "workflow_step_runs", ["run_id"])
    op.create_index("ix_workflow_step_runs_tenant_id", "workflow_step_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("workflow_step_runs")
    op.drop_table("workflow_runs")
