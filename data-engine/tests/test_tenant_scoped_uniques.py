"""Las unique de fund_managers y dividend_records tienen que ser por tenant.

`Company` es global (el `cik` de un emisor es el mismo para todos los tenants),
pero `fund_managers` y `dividend_records` son TenantOwnedMixin. Con el unique
solo sobre la columna compartida:

  fund_managers   el servicio hace `select(FundManager).where(FundManager.cik ==
                  cik)`. El with_loader_criteria oculta al tenant B la fila del
                  tenant A, asi que B ve None e inserta -> IntegrityError. El
                  tenant B no puede ingerir 13F de ningun emisor.

  dividend_records el IntegrityError sale en el commit de sync_company, fuera
                  del try, y aborta el barrido de toda la cartera.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from sqlalchemy import inspect

from app.core.database import init_db
from app.models import DividendRecord, FundManager, ManagerHolding

MODELS = pathlib.Path(__file__).resolve().parents[1] / "app" / "models" / "entities.py"


def _unique_constraints(model) -> set[tuple[str, ...]]:
    return {
        tuple(c.name for c in constraint.columns)
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_fund_manager_unique_includes_tenant():
    uniques = _unique_constraints(FundManager)
    assert ("tenant_id", "cik") in uniques, (
        f"uq de fund_managers no incluye tenant_id: {uniques}. El tenant B "
        "reventaria con IntegrityError al ingerir 13F."
    )
    assert ("cik",) not in uniques


def test_dividend_record_unique_includes_tenant():
    uniques = _unique_constraints(DividendRecord)
    assert ("tenant_id", "company_id", "ex_date", "amount") in uniques, (
        f"uq de dividend_records no incluye tenant_id: {uniques}"
    )
    assert ("company_id", "ex_date", "amount") not in uniques


@pytest.mark.parametrize("model", [DividendRecord, FundManager, ManagerHolding])
def test_tenant_id_is_indexed(model):
    indexes = {
        tuple(col.name for col in index.columns)
        for index in model.__table__.indexes
    }
    assert ("tenant_id",) in indexes, (
        f"{model.__tablename__} no tiene indice en tenant_id: toda consulta "
        "de ese servicio es un seq scan"
    )


# --------------------------------------------------------------------------
# El esquema migrado y el ORM tienen que coincidir
# --------------------------------------------------------------------------


def test_migrated_schema_matches_the_orm_for_these_uniques():
    """Verifica el esquema REALMENTE migrado, no el metadata del ORM.

    SQLite declara los UNIQUE en linea dentro del CREATE TABLE, asi que hay que
    leer `sqlite_master.sql` de la tabla y no los indices sueltos. La base se
    construye con la cadena de migraciones completa, asi que esto falla si
    0032 no materializa lo que entities.py declara.
    """
    import os
    import sqlite3
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    data_engine = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migrated.db"
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "APP_ENV": "test",
            "WORKERS_ENABLED": "false",
        }
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=data_engine,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"alembic upgrade head fallo:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

        conn = sqlite3.connect(db_path)
        try:
            expected = {
                "fund_managers": [
                    "uq_fund_manager_tenant_cik UNIQUE (tenant_id, cik)",
                ],
                "dividend_records": [
                    "uq_dividend_record_tenant UNIQUE (tenant_id, company_id, ex_date, amount)",
                ],
            }
            for table, clauses in expected.items():
                row = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert row is not None, f"la tabla {table} no existe tras migrar"
                ddl = " ".join(row[0].split())
                for clause in clauses:
                    assert clause in ddl, (
                        f"{table}: el esquema migrado no declara '{clause}'. "
                        f"DDL: {ddl[-400:]}"
                    )
                # Y el unique global anterior no puede seguir ahi.
                assert "uq_fund_manager_cik" not in ddl or table != "fund_managers"
        finally:
            conn.close()


def test_orm_and_migration_agree_on_constraint_names():
    """El nombre del unique tiene que existir en los dos lados."""
    orm_names = {
        c.name
        for c in DividendRecord.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    } | {
        c.name
        for c in FundManager.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert "uq_dividend_record_tenant" in orm_names
    assert "uq_fund_manager_tenant_cik" in orm_names

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0032_tenant_uniques_fk_actions.py"
    ).read_text(encoding="utf-8")
    for name in orm_names:
        assert name in source, f"{name} existe en el ORM pero no en 0032"


def test_company_stays_global_and_untenanted():
    """Guarda de contrato: Company es global a proposito, no es un descuido."""
    from app.models import Company
    from app.models.entities import TenantOwnedMixin

    assert not issubclass(Company, TenantOwnedMixin)
    assert "tenant_id" not in Company.__table__.columns


def test_three_tables_are_tenant_owned():
    """Guarda de contrato: las tres son tenant-owned, luego su unique lo es."""
    from app.models.entities import TenantOwnedMixin

    for model in (DividendRecord, FundManager, ManagerHolding):
        assert issubclass(model, TenantOwnedMixin), model.__name__
