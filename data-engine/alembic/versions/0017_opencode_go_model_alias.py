"""migrate the application model registry to OpenCode Go

Revision ID: 0017_opencode_go_model_alias
Revises: 0016_principle_jobs_snapshots
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0017_opencode_go_model_alias"
down_revision = "0016_principle_jobs_snapshots"
branch_labels = None
depends_on = None

# HISTORICO DESTRUCTIVO — no reescribir: el upgrade() borra TODAS las filas
# de model_aliases (table.delete() sin WHERE) y deja solo la fila
# provider='opencode-go'; cualquier alias custom previo se pierde.
# El downgrade() tampoco restaura: solo elimina las filas 'opencode-go'.
# Comportamiento documentado y cubierto en
# tests/test_0017_destructive_migration_documented.py.


def upgrade() -> None:
    table = sa.table(
        "model_aliases",
        sa.column("internal_alias", sa.String(120)),
        sa.column("provider", sa.String(40)),
        sa.column("provider_model_id", sa.String(240)),
        sa.column("enabled", sa.Boolean()),
        sa.column("context_window", sa.Integer()),
        sa.column("input_cost", sa.Numeric(18, 6)),
        sa.column("output_cost", sa.Numeric(18, 6)),
        sa.column("supported_capabilities", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.execute(table.delete())
    now = datetime.now(UTC)
    op.bulk_insert(
        table,
        [
            {
                "internal_alias": "deepseek-v4-flash",
                "provider": "opencode-go",
                "provider_model_id": "deepseek-v4-flash",
                "enabled": True,
                "context_window": 1_048_576,
                "input_cost": 0,
                "output_cost": 0,
                "supported_capabilities": [
                    "text",
                    "reasoning",
                    "tool_calling",
                    "structured_output",
                ],
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    table = sa.table("model_aliases", sa.column("provider", sa.String(40)))
    op.execute(table.delete().where(table.c.provider == "opencode-go"))
