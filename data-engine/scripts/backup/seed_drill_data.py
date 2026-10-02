"""Siembra DETERMINISTA para el drill de backup/restore (local y CI).

Los datos sembrados son los que el restore tiene que recuperar: 12 companies, 7
objetos en MinIO con claves conocidas y una coleccion de Qdrant con 25 puntos de
dimension 8. Si el restore pierde una fila, el conteo se va de 12 a 11 y la
verificacion falla; si pierde una dimension, tambien.

Es el MISMO sembrador que usa `disaster_drill.py` (el drill lo importa) y que usa
el workflow `restore-drill.yml` (que lo ejecuta como modulo). Un solo sitio
define "que datos hay", para que el drill y CI no puedan divergir.

Uso (los parametros vienen del entorno, que es como los fija el workflow):
    python -m scripts.backup.seed_drill_data

Variables con default (los del compose de desarrollo):
    DRILL_DATABASE_URL, DRILL_MINIO_ENDPOINT, DRILL_MINIO_ACCESS_KEY,
    DRILL_MINIO_SECRET_KEY, DRILL_BUCKET, DRILL_QDRANT_URL, DRILL_COLLECTION,
    DRILL_COMPANIES, DRILL_OBJECTS, DRILL_POINTS, DRILL_DIM
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import DATA_ENGINE_ROOT, FailClosedError, redact, require, run  # noqa: E402

# --- Datos del drill (una sola definicion; el drill y CI los importan) --------

SEED_COMPANIES = 12
SEED_OBJECTS = 7
SEED_POINTS = 25
SEED_DIM = 8
SEED_BUCKET = "research"
SEED_COLLECTION = "portfolio_research_documents"
SEED_TICKERS = tuple(f"DRL{index:04d}" for index in range(1, SEED_COMPANIES + 1))
SEED_KEYS = tuple(
    f"tenant-1/DRL{index:04d}/filings/annual-{index:04d}.pdf"
    for index in range(1, SEED_OBJECTS + 1)
)

DEFAULT_DATABASE_URL = "postgresql+psycopg://portfolio:portfolio@127.0.0.1:5432/cavaai_drill_source"
DEFAULT_MINIO_ENDPOINT = "127.0.0.1:9000"
DEFAULT_MINIO_ACCESS_KEY = "portfolio"
DEFAULT_MINIO_SECRET_KEY = "portfoliosecret"
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"


def seed_postgres(database_url: str, *, cwd: Path | None = None, python: str | None = None) -> None:
    """Migraciones Alembic + N companies, usando los MODELOS de la app.

    Se siembla con los modelos y no con SQL a mano para que el drill no se rompa
    cada vez que una migracion anade una columna obligatoria: si el esquema y el
    modelo divergen, aqui falla y con un mensaje util.
    """
    root = cwd or DATA_ENGINE_ROOT
    env = _seed_env(database_url, root)
    run(
        [python or sys.executable, "-m", "alembic", "upgrade", "head"],
        timeout=1800,
        env=env,
        what="alembic upgrade head",
        cwd=root,
    )
    script = "\n".join(
        [
            "from app.core.database import SessionLocal",
            "from app.models import Company",
            "from sqlalchemy import select",
            f"tickers = {SEED_TICKERS!r}",
            "session = SessionLocal()",
            "existing = set(session.scalars(select(Company.ticker)).all())",
            "for ticker in tickers:",
            "    if ticker in existing:",
            "        continue",
            "    session.add(Company(",
            "        ticker=ticker, name=f'Drill {ticker}', exchange='DRILL',",
            "        currency='USD', sector='Drill', industry='Drill',",
            "        company_type='Operating', valuation_model='dcf',",
            "    ))",
            "session.commit()",
            "found = session.scalars(",
            "    select(Company.ticker).where(Company.ticker.in_(tickers))",
            ").all()",
            f"assert len(found) == {SEED_COMPANIES}, f'la siembra dejo {{len(found)}} companies'",
            "session.close()",
            f"print('siembra postgres: {SEED_COMPANIES} companies')",
        ]
    )
    _run_in_root(python or sys.executable, script, env, root)


def _seed_env(database_url: str, root: Path) -> dict[str, str]:
    """Entorno de la siembra: `app` solo es importable con data-engine/ en el path."""
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    env.setdefault("APP_ENV", "test")
    env.setdefault("RESEARCH_AUTH_REQUIRED", "false")
    env.setdefault("WORKERS_ENABLED", "false")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + existing if existing else "")
    return env


def _run_in_root(interpreter: str, script: str, env: dict[str, str], root: Path) -> None:
    """Ejecuta el script de siembra con `data-engine/` como directorio de trabajo."""
    proc = subprocess.run(  # noqa: S603 - argv explicito, sin shell
        [interpreter, "-c", script],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
        check=False,
    )
    if proc.returncode != 0:
        tail = redact((proc.stderr or proc.stdout).strip().splitlines()[-6:])
        raise FailClosedError(
            f"la siembra de companies fallo (codigo {proc.returncode}): " + "\n".join(tail)
        )
    print(f"[seed] {proc.stdout.strip()}")


def seed_minio(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str = SEED_BUCKET,
) -> None:
    """M objetos con claves conocidas y contenido determinista."""
    from scripts.backup.backup_minio import build_client

    client = build_client(endpoint, access_key, secret_key)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    for index, key in enumerate(SEED_KEYS, start=1):
        payload = f"contenido determinista del drill, objeto {index}\n".encode()
        client.put_object(
            bucket,
            key,
            io.BytesIO(payload),
            length=len(payload),
            content_type="application/pdf",
        )
    print(f"[seed] siembra minio: {len(SEED_KEYS)} objetos en '{bucket}'")


def seed_qdrant(
    url: str,
    collection: str = SEED_COLLECTION,
    *,
    points: int = SEED_POINTS,
    dim: int = SEED_DIM,
) -> None:
    """P puntos de dimension D con ids enteros deterministas."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - dependencia declarada
        raise FailClosedError("falta httpx para sembrar Qdrant") from exc
    base = url.rstrip("/")
    with httpx.Client(timeout=120) as client:
        client.delete(f"{base}/collections/{collection}")
        response = client.put(
            f"{base}/collections/{collection}",
            json={"vectors": {"size": dim, "distance": "Cosine"}},
        )
        require(
            response.status_code < 400,
            f"crear la coleccion de drill: HTTP {response.status_code}: {response.text[:200]}",
        )
        payload = {
            "points": [
                {
                    "id": index,
                    "vector": [float((index + axis) % 7) for axis in range(dim)],
                    "payload": {"ticker": SEED_TICKERS[index % len(SEED_TICKERS)], "n": index},
                }
                for index in range(points)
            ]
        }
        response = client.put(f"{base}/collections/{collection}/points?wait=true", json=payload)
        require(
            response.status_code < 400,
            f"insertar puntos de drill: HTTP {response.status_code}: {response.text[:200]}",
        )
        counted = int(client.get(f"{base}/collections/{collection}").json()["result"]["points_count"])
        require(
            counted == points,
            f"la siembra dejo {counted} puntos en Qdrant, se esperaban {points}",
        )
    print(f"[seed] siembra qdrant: {points} puntos de dimension {dim} en '{collection}'")


def seed_from_env() -> None:
    """Siembra los tres pilares con lo que hay en el entorno."""
    seed_postgres(os.environ.get("DRILL_DATABASE_URL", DEFAULT_DATABASE_URL))
    seed_minio(
        os.environ.get("DRILL_MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT),
        os.environ.get("DRILL_MINIO_ACCESS_KEY", DEFAULT_MINIO_ACCESS_KEY),
        os.environ.get("DRILL_MINIO_SECRET_KEY", DEFAULT_MINIO_SECRET_KEY),
        bucket=os.environ.get("DRILL_BUCKET", SEED_BUCKET),
    )
    seed_qdrant(
        os.environ.get("DRILL_QDRANT_URL", DEFAULT_QDRANT_URL),
        os.environ.get("DRILL_COLLECTION", SEED_COLLECTION),
        points=int(os.environ.get("DRILL_POINTS", SEED_POINTS)),
        dim=int(os.environ.get("DRILL_DIM", SEED_DIM)),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        seed_from_env()
    except FailClosedError as exc:
        print(f"[seed] FALLO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
