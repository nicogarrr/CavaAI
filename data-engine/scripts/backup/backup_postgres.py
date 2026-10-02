"""Backup VERIFICADO de Postgres: dump custom + globals + evidencia de esquema.

Por que `-Fc` y no un dump plano: el formato custom va comprimido y, sobre
todo, es SELECCIONABLE. `pg_restore` puede restaurar una sola tabla de un dump
corrupto a medias y `--list` da el catalogo del artefacto sin tocar el servidor.
Un dump plano no se puede leer sin restaurarlo entero.

Que se declara en el manifiesto: revision de Alembic de la base VIVA (comparada
con el head del codigo), conteos por tabla leidos ANTES y DESPUES del dump (para
detectar escrituras concurrentes y no producir un backup inconsistente),
checksum SHA-256 y tamano de cada artefacto.

Uso:
    python -m scripts.backup.backup_postgres --out backups/<id>
    python -m scripts.backup.backup_postgres --out backups/<id> \\
        --mode local --host 127.0.0.1 --user portfolio --database cavaai_research
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    PG_DUMP_FORMAT,
    PG_DUMP_FORMAT_FLAG,
    POSTGRES_IMAGE,
    REQUIRED_PG_CLIENT_MAJOR,
    Artifact,
    FailClosedError,
    ManifestBuilder,
    PsqlTarget,
    alembic_head,
    check_pg_client_version,
    discover_postgres_container,
    exit_with,
    parse_pg_tool_version,
    redact,
    require,
    sha256_file,
    tool_version,
)

PILLAR = "postgres"
DUMP_RELPATH = "postgres/database.dump"
GLOBALS_RELPATH = "postgres/globals.sql"

_COUNT_QUERY = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
)
#: Tabla+columna con las que el verify_restore prueba el endpoint de datos.
#: Probar que la API responde 200 con una lista vacia no demuestra que sirva lo
#: restaurado; probar que devuelve un ticker que estaba en el backup, si.
PROBE_TABLE = "companies"
PROBE_COLUMN = "ticker"
PROBE_LIMIT = 5


def resolve_target(
    *,
    database: str,
    user: str,
    mode: str,
    container: str | None,
    host: str | None,
    port: int | None,
    password: str | None,
) -> PsqlTarget:
    """Construye el `PsqlTarget` y resuelve el contenedor si hace falta."""
    import shutil

    resolved = mode
    if resolved == "auto":
        if container:
            resolved = "docker"
        elif shutil.which("pg_dump"):
            resolved = "local"
        else:
            resolved = "docker"
    if resolved == "docker" and not container:
        container = discover_postgres_container()
    if resolved == "local":
        require(bool(host), "modo local sin --host")
    return PsqlTarget(
        mode=resolved,
        database=database,
        user=user,
        container=container,
        host=host,
        port=port,
        password=password,
    )


def list_tables(target: PsqlTarget) -> list[str]:
    """Tablas BASE del esquema public."""
    return [
        line.strip()
        for line in target.psql_value(_COUNT_QUERY).splitlines()
        if line.strip()
    ]


def table_counts(target: PsqlTarget, *, tables: list[str] | None = None) -> dict[str, int]:
    """`{tabla: filas}` en UNA sola consulta.

    El esquema tiene ~180 tablas y en modo docker cada consulta es un
    `docker exec` (~1 s en Docker Desktop): 180 count(*) sueltos convertian el
    backup en 10 minutos de esperas. Un `UNION ALL` de todos los count(*) lo
    deja en una llamada, y el codigo que compara los conteos es el mismo en el
    backup y en el verify.
    """
    names = tables if tables is not None else list_tables(target)
    if not names:
        return {}
    for name in names:
        require(
            "|" not in name,
            f"la tabla {name!r} contiene el separador de salida de psql: "
            "el conteo seria ilegible",
        )
    union = "\nUNION ALL\n".join(f"SELECT '{name}' AS t, count(*) AS c FROM \"{name}\"" for name in names)
    rows = target.psql_value(f"SELECT t, c FROM ({union}) AS cavaai_counts ORDER BY t")
    counts: dict[str, int] = {}
    for line in rows.splitlines():
        if not line.strip():
            continue
        name, _, value = line.strip().partition("|")
        require(
            value.strip().isdigit(),
            f"conteo ilegible de la tabla {name!r}: {value!r} (¿fallo la consulta?)",
        )
        counts[name.strip()] = int(value.strip())
    missing = sorted(set(names) - set(counts))
    require(not missing, f"la consulta de conteos no devolvio las tablas {missing}")
    return counts


def live_alembic_version(target: PsqlTarget) -> str:
    value = target.psql_value("SELECT version_num FROM alembic_version")
    require(
        bool(value),
        "la base no tiene fila en alembic_version: no es una base migrada. "
        "Ejecuta `python -m alembic upgrade head` antes de respaldar",
    )
    return value.splitlines()[0].strip()


def probe_values(target: PsqlTarget) -> list[str]:
    """Valores de `companies.ticker` para probar el endpoint de datos tras el restore."""
    present = target.psql_value(
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = 'public' AND table_name = '{PROBE_TABLE}'"
    )
    if present != "1":
        return []
    value = target.psql_value(
        f'SELECT {PROBE_COLUMN} FROM "{PROBE_TABLE}" ORDER BY 1 LIMIT {PROBE_LIMIT}'
    )
    return [line.strip() for line in value.splitlines() if line.strip()]


def dump_to_file(target: PsqlTarget, dump_path: Path, database: str) -> None:
    """Escribe el dump en disco alimentando `pg_dump` por stdout.

    `pg_dump -f <ruta>` escribiria DENTRO del contenedor; el dump tiene que
    quedar en el host (o en el directorio de backup del drill) para poder
    hashearlo y para que el restore lo lea desde donde sea.
    """
    argv = target.argv("pg_dump", PG_DUMP_FORMAT_FLAG, "--no-owner", f"--dbname={database}")
    env = dict(os.environ)
    env.update(target.env())
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with dump_path.open("wb") as handle:
        proc = subprocess.run(  # noqa: S603 - argv explicito, sin shell
            argv,
            stdout=handle,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
    if proc.returncode != 0:
        tail = redact(proc.stderr.decode("utf-8", errors="replace").strip())
        raise FailClosedError(
            f"pg_dump -Fc salio con codigo {proc.returncode}: "
            + "\n".join(tail.splitlines()[-6:])
        )
    require(dump_path.stat().st_size > 0, "pg_dump -Fc produjo un fichero vacio")


def dump_globals(target: PsqlTarget, backup_dir: Path) -> Artifact:
    """`pg_dumpall --globals-only`: roles y privilegios del cluster.

    Sin esto, un restore en un cluster NUEVO deja la base restaurada pero sin
    el rol que la usa, y el backend falla con "role does not exist" en el
    primer arranque: un restore que "funciona" y luego rompe.
    """
    result = target.cluster_wide().run_tool(
        "pg_dumpall",
        "--globals-only",
        "--no-role-passwords",
        timeout=300,
        what="pg_dumpall --globals-only",
    )
    path = backup_dir / GLOBALS_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout, encoding="utf-8")
    return Artifact(
        pillar=PILLAR,
        path=GLOBALS_RELPATH,
        format="pg_dumpall_globals",
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        kind="full",
        detail="roles y privilegios del cluster (sin contrasenas)",
    )


def run_backup(
    backup_dir: Path,
    *,
    database: str,
    user: str,
    mode: str = "auto",
    container: str | None = None,
    host: str | None = None,
    port: int | None = None,
    password: str | None = None,
    backup_kind: str = "full",
    with_globals: bool = True,
    allow_schema_drift: bool = False,
) -> ManifestBuilder:
    """Ejecuta el backup de Postgres y devuelve el ManifestBuilder con su parte."""
    target = resolve_target(
        database=database,
        user=user,
        mode=mode,
        container=container,
        host=host,
        port=port,
        password=password,
    )

    client_version = target.client_version()
    client_major = parse_pg_tool_version(client_version)
    check_pg_client_version(client_major)
    server_version = tool_version(target.argv("psql"))

    builder = ManifestBuilder(backup_dir=backup_dir, backup_kind=backup_kind)
    builder.add_tool(
        "pg_dump",
        client_version,
        client_major=client_major,
        mode=target.mode,
        container=target.container or "",
        image=POSTGRES_IMAGE,
        required_major=REQUIRED_PG_CLIENT_MAJOR,
        format_flag=PG_DUMP_FORMAT_FLAG,
    )
    builder.add_tool("pg_restore", client_version, client_major=client_major, mode=target.mode)

    before = table_counts(target)
    require(
        bool(before),
        f"{database}: el esquema public no tiene ninguna tabla; "
        "`python -m alembic upgrade head` antes de respaldar",
    )
    live_head = live_alembic_version(target)
    code_head = alembic_head()

    dump_path = backup_dir / DUMP_RELPATH
    dump_to_file(target, dump_path, database)

    after = table_counts(target)
    drifted = {
        name: (before[name], after[name]) for name in before if before[name] != after[name]
    }
    require(
        not drifted,
        "escrituras concurrentes durante el backup: el dump no es consistente con "
        f"los conteos del manifiesto ({drifted}). Reintenta en una ventana sin escritura",
    )

    if live_head != code_head:
        require(
            allow_schema_drift,
            f"la base esta en {live_head} y el codigo en {code_head}: un backup aqui "
            "restauraria un esquema anterior al head y la app romperia al arrancar. "
            "Ejecuta `python -m alembic upgrade head`, o repite con "
            "--allow-schema-drift si el desfase es intencionado",
        )

    builder.add_artifact(
        Artifact(
            pillar=PILLAR,
            path=DUMP_RELPATH,
            format=PG_DUMP_FORMAT,
            sha256=sha256_file(dump_path),
            bytes=dump_path.stat().st_size,
            kind=backup_kind,
            detail=f"base={database} cliente={client_version} servidor={server_version}",
        )
    )
    if with_globals:
        builder.add_artifact(dump_globals(target, backup_dir))

    builder.declare_postgres(
        database=database,
        server_version=server_version,
        alembic_version=live_head,
        code_alembic_head=code_head,
        schema_drift=bool(allow_schema_drift and live_head != code_head),
        table_count=len(before),
        tables=before,
        counts_source="doble lectura de la base viva (antes y despues del dump); drift -> fallo",
        probe_table=PROBE_TABLE,
        probe_column=PROBE_COLUMN,
        probe_values=probe_values(target),
    )
    return builder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup verificado de Postgres (custom format).")
    parser.add_argument("--out", required=True, help="Directorio de backup.")
    parser.add_argument("--database", default="cavaai_research")
    parser.add_argument("--user", default="portfolio")
    parser.add_argument("--mode", choices=("auto", "docker", "local"), default="auto")
    parser.add_argument("--container", default=None, help="Contenedor Postgres (modo docker).")
    parser.add_argument("--host", default=None, help="Host Postgres (modo local).")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--password", default=None, help="Solo local; viaja por PGPASSWORD.")
    parser.add_argument(
        "--kind",
        choices=("full", "incremental"),
        default="full",
        help="Se declara en el manifiesto. 'incremental' exige un artefacto base previo.",
    )
    parser.add_argument("--no-globals", action="store_true", help="No volcar roles del cluster.")
    parser.add_argument(
        "--allow-schema-drift",
        action="store_true",
        help="Respaldar aun con la base por detras del head (queda anotado).",
    )
    parser.add_argument(
        "--fragment-out",
        default=None,
        help="Escribe aqui el fragmento JSON del pilar (lo usa backup_all.py).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        builder = run_backup(
            Path(args.out),
            database=args.database,
            user=args.user,
            mode=args.mode,
            container=args.container,
            host=args.host,
            port=args.port,
            password=args.password,
            backup_kind=args.kind,
            with_globals=not args.no_globals,
            allow_schema_drift=args.allow_schema_drift,
        )
    except FailClosedError as exc:
        return exit_with(f"[backup:{PILLAR}] FALLO: {exc}", False)

    lines = [
        f"[backup:{PILLAR}] ok: {builder.postgres.get('table_count', 0)} tablas declaradas, "
        f"alembic={builder.postgres.get('alembic_version')}"
    ]
    for artifact in builder.artifacts:
        lines.append(f"  - {artifact.path} ({artifact.bytes} B, sha256={artifact.sha256[:12]}...)")
    if args.fragment_out:
        Path(args.fragment_out).write_text(
            json.dumps(
                {
                    "tools": builder.tools,
                    "artifacts": [a.as_dict() for a in builder.artifacts],
                    "postgres": builder.postgres,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return exit_with("\n".join(lines), True)


if __name__ == "__main__":
    raise SystemExit(main())
