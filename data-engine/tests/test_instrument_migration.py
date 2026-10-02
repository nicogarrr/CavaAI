"""0047: upgrade crea instrument_references, downgrade la revierte, upgrade la recrea."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

DATA_ENGINE_DIR = Path(__file__).resolve().parents[1]
REVISION_0046 = "0046_inferred_inputs"
REVISION_0047 = "0047_instrument_references"


def _alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=DATA_ENGINE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr


def test_0047_upgrade_downgrade_upgrade_roundtrip():
    temp_dir = Path(tempfile.mkdtemp(prefix="cavaai_0047_"))
    database_url = f"sqlite:///{(temp_dir / 'instruments.db').as_posix()}"
    try:
        _alembic(database_url, "upgrade", REVISION_0046)
        engine = create_engine(database_url)
        try:
            assert "instrument_references" not in inspect(engine).get_table_names()
        finally:
            engine.dispose()

        _alembic(database_url, "upgrade", REVISION_0047)
        engine = create_engine(database_url)
        try:
            assert "instrument_references" in inspect(engine).get_table_names()
            columns = {c["name"] for c in inspect(engine).get_columns("instrument_references")}
            for expected in ("ticker_normalized", "figi", "isin", "sector",
                             "industry", "country", "exchange", "as_of", "source"):
                assert expected in columns
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO instrument_references (ticker_normalized, figi, as_of, "
                    "source, created_at, updated_at) VALUES "
                    "('SAN.MC', 'BBG000BSAN01', '2026-10-01', 'financedatabase', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
        finally:
            engine.dispose()

        _alembic(database_url, "downgrade", "-1")
        engine = create_engine(database_url)
        try:
            assert "instrument_references" not in inspect(engine).get_table_names()
        finally:
            engine.dispose()

        _alembic(database_url, "upgrade", REVISION_0047)
        engine = create_engine(database_url)
        try:
            assert "instrument_references" in inspect(engine).get_table_names()
        finally:
            engine.dispose()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
