"""0036 research_alerts.last_triggered_at (hora real del ultimo disparo)

ResearchAlert reutiliza la fila por fingerprint en disparos repetidos
(actualiza message/severity/metadata, NO created_at): la hora de creacion
era la del PRIMER disparo y el historial de /alerts la presentaba como
la del ultimo. last_triggered_at se actualiza en cada emision/re-emision.
Backfill con created_at: para filas preexistentes es el unico instante de
disparo conocido y verdadero (el primero); no se fabrica otro.
"""

import sqlalchemy as sa

from alembic import op

revision = "0036_research_alert_last_triggered_at"
down_revision = "0035_market_price_adjclose_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_alerts") as batch_op:
        batch_op.add_column(sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text("UPDATE research_alerts SET last_triggered_at = created_at WHERE last_triggered_at IS NULL")
    )


def downgrade() -> None:
    with op.batch_alter_table("research_alerts") as batch_op:
        batch_op.drop_column("last_triggered_at")
