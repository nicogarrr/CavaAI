"""Backfill de entregas in_app de alertas creadas sin dispatch (idempotente)."""
from alembic import op

revision = "0059_alert_in_app_delivery_backfill"
down_revision = "0058_thesis_projection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        INSERT INTO alert_deliveries
            (tenant_id, alert_id, channel, status, attempts, created_at, updated_at)
        SELECT a.tenant_id, a.id, 'in_app', 'delivered', 1, a.created_at, now()
        FROM research_alerts a
        WHERE a.channels::jsonb ? 'in_app'
          AND NOT EXISTS (
              SELECT 1 FROM alert_deliveries d
              WHERE d.alert_id = a.id AND d.channel = 'in_app'
          )
        """
    )


def downgrade() -> None:
    # Datos verdaderos: no se borran filas de entrega.
    pass
