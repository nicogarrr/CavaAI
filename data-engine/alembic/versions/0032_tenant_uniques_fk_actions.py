"""0032 tenant-scoped uniques and missing tenant indexes

Revision ID: 0032_tenant_uniques_fk_actions
Revises: 0031_propick_runs

Unique constraints globales sobre columnas de datos compartidos, en tablas que
SI son tenant-owned.

`Company` es deliberadamente global (datos de emisor publicos), asi que su `cik`
es el mismo para todos los tenants. Pero:

- `fund_managers` es TenantOwnedMixin y su unique era `uq_fund_manager_cik`
  sobre `cik` solo. Con `with_loader_criteria`, la consulta del servicio
  (`select(FundManager).where(FundManager.cik == cik)`) le oculta al tenant B la
  fila que creo el tenant A, de modo que B ve None e intenta insertar: y eso
  revienta con IntegrityError. El tenant B no puede ingerir 13F de NINGUN
  emisor, y no hay try/except IntegrityError en ese camino
  (manager_holding_ingestion_service.py:74).

- `dividend_records` tenia el mismo patron: `uq_dividend_record` sobre
  (company_id, ex_date, amount) sin tenant_id. El IntegrityError aparece en el
  commit de `sync_company`, fuera del try, asi que aborta el barrido de TODA la
  cartera y se pierden los tickers ya procesados en esa pasada
  (dividend_ingestion_service.py:148).

Ambas pasan a ser tenant-scoped, que es como ya se indexan las demas tablas con
datos de tenant.

Ademas se crean los tres `ix_<tabla>_tenant_id` que el ORM declara y que ninguna
migracion creo: dividend_records, fund_managers y manager_holdings. Los tres
filtran por tenant en cada consulta, asi que sin indice es un seq scan por
consulta.

Lo que esta migracion NO hace (y queda pendiente de una PR con Postgres
disponible para verificarlo):

  entities.py declara 60 FKs con ondelete explicito (22 CASCADE, 38 SET NULL)
  y las migraciones solo materializan 2. Las otras 58 son NO ACTION, de modo que
  el DELETE que el ORM da por hecho que propaga falla con ForeignKeyViolation.
  El caso mas probable en produccion es
  `FinancialIngestionService._replace_fmp_data`, que borra los financial_facts
  de un proveedor antes de reingerir: `financial_facts.id` tiene cinco FKs
  entrantes sin cascada (fact_revisions, kpi_extraction_candidates,
  expectation_reviews, call_claims, management_promises). En SQLite los FK no
  estan activos y en dev nunca se ve; en Postgres, la segunda vez que una
  empresa reingiere tras haberse aprobado un KPI o una revision, revienta
  dentro de un worker de Dramatiq.

  En Postgres, cambiar la accion referencial exige recrear la tabla (no hay
  `ALTER ... ON DELETE`). Con 60 FKs en ~45 tablas eso es la operacion mas
  pesada de toda la cadena, y dado que el CMD del contenedor ejecuta
  `alembic upgrade head` en cada arranque, un fallo ahi tumba el backend. No
  se envia DDL de Postgres sin poder ejecutarlo antes contra Postgres.
"""

from alembic import op

revision = "0032_tenant_uniques_fk_actions"
down_revision = "0031_propick_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # fund_managers: (cik) -> (tenant_id, cik)
    with op.batch_alter_table("fund_managers") as batch:
        batch.drop_constraint("uq_fund_manager_cik", type_="unique")
        batch.create_unique_constraint("uq_fund_manager_tenant_cik", ["tenant_id", "cik"])

    # dividend_records: (company_id, ex_date, amount) -> (+ tenant_id)
    with op.batch_alter_table("dividend_records") as batch:
        batch.drop_constraint("uq_dividend_record", type_="unique")
        batch.create_unique_constraint(
            "uq_dividend_record_tenant",
            ["tenant_id", "company_id", "ex_date", "amount"],
        )

    # Los ix_<tabla>_tenant_id que el ORM declara y faltaban.
    for table in ("dividend_records", "fund_managers", "manager_holdings"):
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"], if_not_exists=True)


def downgrade() -> None:
    # Forward-only a proposito. Volver a los unique globales reabriria el
    # IntegrityError cross-tenant que esta migracion cierra, y un fallo a
    # mitad dejaria constraints a medio migrar. Un rollback real exige
    # deduplicar por tenant primero y verificarlo: operacion deliberada,
    # no un `alembic downgrade`.
    raise RuntimeError(
        "0032_tenant_uniques_fk_actions es forward-only: restaurar los "
        "unique globales exige deduplicar por tenant y verificarlo a mano"
    )
