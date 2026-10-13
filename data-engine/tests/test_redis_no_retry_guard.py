"""Guard: todo cliente Redis del servicio se crea con retry explicito sin reintentos.

El defecto de 3 reintentos (redis-py 6) aplica a ``Redis(host=...)``; ``from_url`` usa
``None`` hoy, asi que ``retry=`` fija el fallo rapido por contrato y evita regresion si
cambia el defecto. Este guard solo vigila ``from_url`` (no el constructor ``Redis(host=...)``;
hoy no hay ninguno en ``app/``). Ver ``app/core/redis_retry.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "app", ROOT / "main.py"]


def _py_files():
    for target in SCAN:
        if target.is_file():
            yield target
        else:
            yield from target.rglob("*.py")


def test_todo_redis_from_url_pasa_retry_sin_reintentos():
    missing = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_from_url = isinstance(func, ast.Attribute) and func.attr == "from_url"
            if not is_from_url:
                continue
            owner = ast.unparse(func.value)
            if "redis" not in owner.lower():
                continue
            kwargs = {kw.arg for kw in node.keywords}
            if "retry" not in kwargs:
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not missing, "from_url de Redis sin retry=no_retry(): " + ", ".join(missing)


def test_no_retry_tiene_cero_reintentos():
    from app.core.redis_retry import no_retry, no_retry_async

    assert no_retry()._retries == 0
    assert no_retry_async()._retries == 0


def test_cliente_creado_con_no_retry_no_reintenta():
    import redis

    from app.core.redis_retry import no_retry

    client = redis.from_url("redis://localhost:6379/0", retry=no_retry())
    try:
        assert client.get_retry()._retries == 0
    finally:
        client.close()
