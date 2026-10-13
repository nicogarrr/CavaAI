"""Renombra definition_version MARCO_NICO_V1/V2 a MARCO_V1/V2 en calculated_metrics.

Si ya existe la fila nueva para la misma clave (tenant, empresa, metrica, periodo),
la antigua se borra para respetar uq_calculated_metric_definition_period; si no, se renombra.
"""
import sqlalchemy as sa

from alembic import op

revision = "0060_marco_version_rename"
down_revision = "0059_alert_in_app_delivery"
branch_labels = None
depends_on = None

RENAMES = (("MARCO_NICO_V1", "MARCO_V1"), ("MARCO_NICO_V2", "MARCO_V2"))


def rename_version(conn, old: str, new: str) -> None:
    conn.execute(
        sa.text(
            """
            DELETE FROM calculated_metrics WHERE definition_version = :old AND EXISTS (
                SELECT 1 FROM calculated_metrics n
                WHERE n.definition_version = :new
                  AND n.tenant_id = calculated_metrics.tenant_id
                  AND n.company_id = calculated_metrics.company_id
                  AND n.metric = calculated_metrics.metric
                  AND n.period = calculated_metrics.period)
            """
        ),
        {"old": old, "new": new},
    )
    conn.execute(
        sa.text("UPDATE calculated_metrics SET definition_version = :new WHERE definition_version = :old"),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    for old, new in RENAMES:
        rename_version(op.get_bind(), old, new)


def downgrade() -> None:
    for old, new in RENAMES:
        rename_version(op.get_bind(), new, old)
