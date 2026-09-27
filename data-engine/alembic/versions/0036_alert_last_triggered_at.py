"""0036 research_alerts.last_triggered_at (hora real del ultimo disparo)

ResearchAlert reutiliza la fila por fingerprint en disparos repetidos
(actualiza message/severity/metadata, NO created_at): la hora de creacion
era la del PRIMER disparo y el historial de /alerts la presentaba como
la del ultimo. last_triggered_at se actualiza en cada emision/re-emision.

SIN backfill: para una fila preexistente con varios disparos previos se
desconoce la hora del ultimo; copiar created_at la mostraria bajo la
etiqueta «ultimo disparo» siendo la del primero. NULL es lo honesto y la
UI etiqueta el fallback como «Creada», sin afirmar ultimo.
"""

import sqlalchemy as sa

from alembic import op

revision = "0036_alert_last_triggered_at"
down_revision = "0035_market_price_adjclose_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_alerts") as batch_op:
        batch_op.add_column(sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research_alerts") as batch_op:
        batch_op.drop_column("last_triggered_at")
