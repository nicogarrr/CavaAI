"""0017: la migracion destructiva es historia — este test la documenta.

NO reescribir 0017_opencode_go_model_alias: el upgrade() borra todas las
filas de model_aliases y deja solo provider='opencode-go'; el downgrade()
solo elimina esas filas sin restaurar nada. Perdida documentada, no bug.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

DATA_ENGINE_DIR = Path(__file__).resolve().parents[1]
REVISION_0016 = "0016_principle_jobs_snapshots"
REVISION_0017 = "0017_opencode_go_model_alias"


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


def _aliases(database_url: str) -> list[tuple[str, str]]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return [
                (row.internal_alias, row.provider)
                for row in conn.execute(
                    text("SELECT internal_alias, provider FROM model_aliases")
                )
            ]
    finally:
        engine.dispose()


def test_0017_upgrade_wipes_custom_aliases_and_downgrade_does_not_restore():
    temp_dir = Path(tempfile.mkdtemp(prefix="cavaai_0017_"))
    database_url = f"sqlite:///{(temp_dir / 'destructive.db').as_posix()}"
    try:
        _alembic(database_url, "upgrade", REVISION_0016)
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO model_aliases "
                        "(internal_alias, provider, provider_model_id, enabled, "
                        "context_window, input_cost, output_cost, "
                        "supported_capabilities, created_at, updated_at) "
                        "VALUES ('my-custom-alias', 'custom-provider', "
                        "'custom-model-1', 1, 64000, 1.0, 2.0, '[]', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
        finally:
            engine.dispose()
        assert ("my-custom-alias", "custom-provider") in _aliases(database_url)

        # Upgrade destructivo: el alias custom desaparece, solo queda opencode-go.
        _alembic(database_url, "upgrade", REVISION_0017)
        remaining = _aliases(database_url)
        assert ("my-custom-alias", "custom-provider") not in remaining
        assert ("deepseek-v4-flash", "opencode-go") in remaining

        # Downgrade no restaurador: elimina opencode-go y deja la tabla vacia.
        _alembic(database_url, "downgrade", REVISION_0016)
        assert _aliases(database_url) == []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
