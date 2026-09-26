"""0034 market_prices.volume admite NULL (volumen desconocido honesto)

Las fuentes spot (FMP quote sin volumen, Finnhub quote) no dan el volumen
del dia. Hasta aqui la fila se escribia con volume=0: un dato fabricado que
coronaba al ticker como el menos activo en movers y ensuciaba "Mas activas"
con ceros. NULL es la representacion honesta de "la fuente no lo da".
Las filas historicas con 0 NO se reescriben aqui: no se puede distinguir un
0 real de un 0 fabricado sin la fuente; su limpieza es decision de datos.
"""

import sqlalchemy as sa

from alembic import op

revision = "0034_market_price_volume_nullable"
down_revision = "0033_alert_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("market_prices", "volume", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Los NULL no caben de vuelta: reescribirlos a 0 fabricaria el dato que
    # esta migracion elimina, asi que el downgrade exige limpiarlos antes.
    op.execute("DELETE FROM market_prices WHERE volume IS NULL")
    op.alter_column("market_prices", "volume", existing_type=sa.Integer(), nullable=False)
