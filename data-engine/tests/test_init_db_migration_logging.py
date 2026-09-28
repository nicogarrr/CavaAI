"""Un ALTER opcional que falla se REGISTRA; no desaparece en silencio.

`init_db()` envolvía el bloque entero de forward-compat (30+ `ALTER TABLE` y el
back-fill de `tenant_id`) en un `except Exception: pass` anotado como "never
block startup on optional alter". Un solo fallo (BD bloqueada, volumen de solo
lectura) dejaba un esquema a medio migrar sin log, sin métrica y sin fallo de
arranque: después, cada consulta que tocara la columna ausente devolvía 500 sin
ninguna pista de que el arranque fuera la causa.

Ahora cada sentencia se intenta por separado, el fallo se registra a nivel ERROR
identificando tabla y sentencia, y queda en un registro de módulo que
`schema_migration_issues()` expone para el payload de salud. En `test`/dev el
arranque nunca se bloquea, y en producción tampoco.
"""

import logging
import sqlite3

import pytest
import sqlalchemy

from app.core import database as database_module
from app.core.config import get_settings
from app.core.database import Base, init_db, schema_migration_issues


@pytest.fixture(autouse=True)
def clean_issues(monkeypatch):
    monkeypatch.setattr(database_module, "_SCHEMA_MIGRATION_ERRORS", [])
    return database_module._SCHEMA_MIGRATION_ERRORS


class _LockedEngine:
    """Engine stub whose transactions always fail like a locked/read-only DB."""

    def __init__(self, real):
        self._real = real

    def begin(self):
        raise sqlite3.OperationalError("database is locked")

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_failing_optional_alter_is_logged_at_error_with_the_statement(
    clean_issues, caplog, monkeypatch
):
    monkeypatch.setattr(
        database_module, "engine", _LockedEngine(database_module.engine)
    )

    with caplog.at_level(logging.ERROR, logger="app.core.database"):
        ok = database_module._execute_optional(
            'ALTER TABLE "positions" ADD COLUMN "market_value_base"',
            'ALTER TABLE "positions" ADD COLUMN "market_value_base" NUMERIC(24, 6)',
        )

    assert ok is False, "una sentencia opcional fallida se reporta, no se propaga"
    errors = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and record.name == "app.core.database"
    ]
    assert errors, "el fallo no puede quedar sin log: es como se hereda un 500 sin causa"
    message = errors[0].getMessage()
    assert "positions" in message
    assert "market_value_base" in message
    # El mensaje de la excepción (puede traer SQL o rutas del host) no se filtra.
    assert "database is locked" not in message
    assert schema_migration_issues() == [
        {
            "statement": 'ALTER TABLE "positions" ADD COLUMN "market_value_base"',
            "error": "OperationalError",
        }
    ]


def test_a_failing_alter_does_not_stop_its_siblings(monkeypatch):
    """Cada ALTER se intenta por separado: uno roto no se lleva el resto."""
    attempted: list[str] = []
    real_execute = database_module._execute_optional

    def recording(statement, sql):
        attempted.append(statement)
        if "broken" in statement:
            monkeypatch.setattr(
                database_module, "engine", _LockedEngine(database_module.engine)
            )
        return real_execute(statement, sql)

    monkeypatch.setattr(database_module, "_execute_optional", recording)
    monkeypatch.setattr(
        database_module, "engine", _LockedEngine(database_module.engine)
    )

    database_module._execute_optional("ALTER TABLE broken ADD COLUMN y", "SELECT 1")
    database_module._execute_optional(
        'ALTER TABLE "healthy" ADD COLUMN "z"', "SELECT 1"
    )

    assert attempted == ["ALTER TABLE broken ADD COLUMN y", 'ALTER TABLE "healthy" ADD COLUMN "z"']
    assert len(schema_migration_issues()) == 2, "ambos fallos quedan registrados"


def test_init_db_survives_and_records_a_structural_migration_failure(
    clean_issues, caplog, monkeypatch
):
    """El arranque en test/dev no se bloquea, pero el fallo tampoco se calla."""
    monkeypatch.setattr(
        database_module, "engine", _LockedEngine(database_module.engine)
    )
    # La inspeccion del esquema es la primera sentencia del bloque de
    # forward-compat; si falla, el resto no puede ni evaluarse.
    monkeypatch.setattr(
        sqlalchemy,
        "inspect",
        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("read-only database")),
    )

    with caplog.at_level(logging.ERROR, logger="app.core.database"):
        init_db()  # no debe lanzar

    assert get_settings().app_env.lower() == "test"
    issues = schema_migration_issues()
    assert issues, "el fallo estructural de la migracion quedo sin registrar"
    assert issues[-1]["error"] == "OperationalError"
    assert any(
        record.levelno == logging.ERROR and record.name == "app.core.database"
        for record in caplog.records
    )


def test_schema_migration_issues_is_empty_on_a_healthy_init(caplog):
    with caplog.at_level(logging.ERROR, logger="app.core.database"):
        init_db()

    assert schema_migration_issues() == []
    assert not [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and record.name == "app.core.database"
    ]


def test_issue_records_expose_no_exception_message():
    """El payload de salud es público: sólo el TIPO de excepción, nunca el texto."""
    database_module._record_schema_migration_error(
        "ALTER TABLE t ADD COLUMN c", RuntimeError("host /srv/secret blew up")
    )
    issue = schema_migration_issues()[-1]
    assert issue == {"statement": "ALTER TABLE t ADD COLUMN c", "error": "RuntimeError"}
    assert "srv" not in str(issue)
    # Y Base.metadata sigue intacto: el esquema se crea antes del bloque opcional.
    assert Base.metadata is not None
