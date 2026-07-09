import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_research_memory_tables():
    data_engine_dir = Path(__file__).resolve().parents[1]
    temp_dir = Path(tempfile.mkdtemp(prefix="cavaai_migration_"))
    database_url = f"sqlite:///{(temp_dir / 'migration.db').as_posix()}"
    env = {**os.environ, "DATABASE_URL": database_url}

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=data_engine_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

        assert result.returncode == 0, result.stderr

        engine = create_engine(database_url)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert {
        "claims",
        "claim_evidence",
        "thesis_sections",
        "thesis_changes",
        "research_sessions",
        "memory_items",
        "calculated_metrics",
    }.issubset(tables)
