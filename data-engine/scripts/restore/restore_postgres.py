"""Restore DESTRUCTIVO de Postgres desde el backup, a un destino limpio.

"Destino limpio" es el caso real de disaster recovery: la base destino esta
vacia (o no existe). Por eso el restore hace `DROP DATABASE` + `CREATE DATABASE`
en vez de sobrescribir encima, y por eso exige `--confirm-restore`.

Verificacion previa (fail-closed): el dump y los globals tienen que casar con
el SHA-256 del manifiesto. Un artefacto corrupto en disco se detecta ANTES de
tocar el destino.

Se restauran los globals (roles) antes que el dump: en un cluster nuevo, sin
el rol, el backend falla con "role does not exist" en el primer arranque, un
restore que "funciona" y luego rompe.

Que el codigo salga con 0 NO es la prueba: el verificador de verdad es
scripts/restore/verify_restore.py (tablas, conteos, revision de Alembic, app
arrancada, objetos legibles, puntos y dimensiones).

Uso:
    python -m scripts.restore.restore_postgres --manifest backups/<id> \\
        --target-database cavaai_research --confirm-restore
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    FailClosedError,
    PsqlTarget,
    artifacts_by_pillar,
    check_pg_client_version,
    discover_postgres_container,
    load_manifest,
    redact,
    require,
    run,
    verify_artifact,
    wait_until_ready,
)
from scripts.backup.backup_postgres import table_counts  # noqa: E402

PILLAR = "postgres"
DUMP_FORMAT = "pg_dump_custom"
GLOBALS_FORMAT = "pg_dumpall_globals"


def find_artifact(manifest: dict, fmt: str, *, required: bool = True) -> dict | None:
    """El (unico) artefacto del pilar con ese formato.

    Fail-closed: por defecto, si no esta o hay mas de uno, FALLA. Sin el no se
    sabe que restaurar, y un `None` silencioso seria un restore que no restaura.
    Los globals son opcionales y por eso se piden con `required=False`.
    """
    matches = [a for a in artifacts_by_pillar(manifest, PILLAR) if a["format"] == fmt]
    require(
        len(matches) <= 1,
        f"el manifiesto declara {len(matches)} artefactos '{fmt}': no se sabe cual restaurar",
    )
    if not matches and required:
        raise FailClosedError(
            f"el manifiesto no declara un artefacto '{fmt}': sin el no hay nada que "
            "restaurar (un backup sin dump custom no es restaurable de forma fiable)"
        )
    return matches[0] if matches else None


def verify_artifacts(backup_dir: Path, manifest: dict) -> None:
    """Cada artefacto del pilar tiene que casar con su checksum antes de tocar nada."""
    for artifact in artifacts_by_pillar(manifest, PILLAR):
        verify_artifact(backup_dir, artifact)


def restore_globals(admin: PsqlTarget, globals_path: Path) -> None:
    """Aplica `pg_dumpall --globals-only`.

    "El rol ya existe" no es motivo para abortar: se ejecutan TODAS las
    sentencias (sin ON_ERROR_STOP) y luego se separa el ruido tolerado del
    error real. Lo que no se tolera es un error de sintaxis o de permisos, que
    invalidaria los globals.
    """
    result = admin.run_tool(
        "psql",
        "-f",
        "-",
        stdin=globals_path.read_text(encoding="utf-8"),
        timeout=300,
        what="restaurar globals (roles)",
        check=False,
    )
    if result.returncode != 0:
        errors = [line for line in result.stderr.splitlines() if "error" in line.lower()]
        fatal = [line for line in errors if "already exists" not in line.lower()]
        require(
            not fatal,
            "pg_dumpall de globals fallo con errores reales: " + redact("\n".join(fatal[:5])),
        )
    print(f"[restore:{PILLAR}] roles del cluster restaurados")


def recreate_database(admin: PsqlTarget, database: str) -> None:
    """Deja la base destino vacia: la borra y la vuelve a crear.

    Se hace con `psql` y no con `dropdb`/`createdb` porque estas no aceptan
    `--dbname` (interpretan `-d` como base de mantenimiento) y el argv del
    `PsqlTarget` es comun a todas las herramientas de Postgres. `WITH (FORCE)`
    corta las conexiones abiertas: sin el, el restore muere si la app sigue
    conectada a la base que se va a borrar.
    """
    quoted = '"' + database.replace('"', '""') + '"'
    admin.run_tool(
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)",
        timeout=600,
        what="DROP DATABASE",
    )
    print(f"[restore:{PILLAR}] base '{database}' eliminada (destino limpio)")
    admin.run_tool(
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        f"CREATE DATABASE {quoted}",
        timeout=600,
        what="CREATE DATABASE",
    )
    print(f"[restore:{PILLAR}] base '{database}' creada vacia")


def clear_public_schema(admin: PsqlTarget, database: str) -> None:
    """Variante no destructiva del nombre de la base (solo para pruebas locales)."""
    PsqlTarget(
        mode=admin.mode,
        database=database,
        user=admin.user,
        container=admin.container,
        host=admin.host,
        port=admin.port,
        password=admin.password,
    ).run_tool(
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        timeout=600,
        what="limpiar esquema public",
    )
    print(f"[restore:{PILLAR}] esquema public de '{database}' vaciado")


def _stage_dump_into_container(container: str, dump_path: Path) -> str:
    """Copia el dump al contenedor y devuelve su ruta dentro.

    `pg_restore` necesita un fichero. Meterlo por stdin como texto no es una
    opcion (el formato custom es binario), y montar un volumen solo para esto
    haria que el backup dependiera de donde vive el host.
    """
    remote = f"/tmp/cavaai-restore-{dump_path.stem}.dump"
    run(["docker", "cp", str(dump_path), f"{container}:{remote}"], timeout=1800, what="docker cp")
    # `test` NO es una herramienta de Postgres: no puede llevar los
    # `--username/--dbname` que `PsqlTarget.argv` anade a las demas.
    probe = run(
        ["docker", "exec", str(container), "test", "-s", remote],
        timeout=120,
        check=False,
        what="dump copiado al contenedor",
    )
    require(
        probe.returncode == 0,
        f"el dump copiado a {remote} no existe o esta vacio en el contenedor {container}",
    )
    return remote


def run_restore(
    manifest_path: Path,
    *,
    target_database: str | None = None,
    user: str = "portfolio",
    mode: str = "auto",
    container: str | None = None,
    host: str | None = None,
    port: int | None = None,
    password: str | None = None,
    keep_database: bool = False,
    restore_globals_sql: bool = True,
) -> dict:
    """Restaura Postgres desde el manifiesto y devuelve su informe."""
    manifest = load_manifest(manifest_path)
    backup_dir = manifest_path if manifest_path.is_dir() else manifest_path.parent
    verify_artifacts(backup_dir, manifest)

    dump_artifact = find_artifact(manifest, DUMP_FORMAT)
    globals_artifact = find_artifact(manifest, GLOBALS_FORMAT, required=False)

    database = target_database or str(manifest["postgres"]["database"])
    resolved = mode
    if resolved == "auto":
        import shutil

        resolved = "docker" if (container or not shutil.which("pg_dump")) else "local"
    if resolved == "docker" and not container:
        container = discover_postgres_container()
    if resolved == "local":
        require(bool(host), "modo local sin --host")

    def target_for(dbname: str) -> PsqlTarget:
        return PsqlTarget(
            mode=resolved,
            database=dbname,
            user=user,
            container=container,
            host=host,
            port=port,
            password=password,
        )

    target = target_for(database)
    admin = target_for("postgres")
    # Tras un desastre el contenedor puede llevar segundos o minutos en
    # initdb/WAL recovery. `pg_isready` responderia antes de tiempo.
    wait_until_ready(admin, timeout=300, what=f"Postgres destino {database}")
    check_pg_client_version(target.client_major())

    if globals_artifact is not None and restore_globals_sql:
        restore_globals(admin, backup_dir / globals_artifact["path"])
    if keep_database:
        clear_public_schema(admin, database)
    else:
        recreate_database(admin, database)

    dump_path = backup_dir / dump_artifact["path"]
    if resolved == "docker":
        dump_argument = _stage_dump_into_container(str(container), dump_path)
    else:
        dump_argument = str(dump_path)
    result = target.run_tool(
        "pg_restore",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        dump_argument,
        timeout=3600,
        what="pg_restore",
        check=False,
    )
    require(
        result.returncode == 0,
        f"pg_restore salio con codigo {result.returncode}: "
        + redact("\n".join(result.stderr.strip().splitlines()[-8:])),
    )
    if resolved == "docker":
        run(
            ["docker", "exec", str(container), "rm", "-f", dump_argument],
            timeout=120,
            check=False,
            what="limpiar dump temporal",
        )

    # La comprobacion va contra la base DESTINO: `information_schema` solo
    # ve las tablas de la base a la que esta conectada, asi que contarlas desde
    # `postgres` (la de mantenimiento) daria 0 con un restore correcto.
    restored_tables = table_counts(target)
    missing = sorted(set(manifest["postgres"]["tables"]) - set(restored_tables))
    require(
        not missing,
        f"tras el restore faltan {len(missing)} de las {len(manifest['postgres']['tables'])} "
        f"tablas declaradas en el manifiesto: {missing[:5]}",
    )
    return {
        "pillar": PILLAR,
        "database": database,
        "mode": resolved,
        "dump": dump_artifact["path"],
        "dump_sha256": dump_artifact["sha256"],
        "globals": (globals_artifact or {}).get("path"),
        "tables_restored": len(restored_tables),
        "expected_tables": len(manifest["postgres"]["tables"]),
        "expected_alembic_version": manifest["postgres"]["alembic_version"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore verificado de Postgres a destino limpio.")
    parser.add_argument("--manifest", required=True, help="Directorio del backup o manifest.json.")
    parser.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Obligatorio: el restore borra la base de destino.",
    )
    parser.add_argument(
        "--target-database",
        default=None,
        help="Base destino (por defecto, la del backup).",
    )
    parser.add_argument("--user", default="portfolio")
    parser.add_argument("--mode", choices=("auto", "docker", "local"), default="auto")
    parser.add_argument("--container", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="No recrear la base: vaciar el esquema public (pruebas locales, no DR).",
    )
    parser.add_argument("--no-globals", action="store_true", help="No restaurar los roles.")
    parser.add_argument("--report-out", default=None, help="Escribe el informe JSON aqui.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_restore:
        print("FALLO: falta --confirm-restore. El restore borra la base de destino.", file=sys.stderr)
        return 1
    try:
        report = run_restore(
            Path(args.manifest),
            target_database=args.target_database,
            user=args.user,
            mode=args.mode,
            container=args.container,
            host=args.host,
            port=args.port,
            password=args.password,
            keep_database=args.keep_database,
            restore_globals_sql=not args.no_globals,
        )
    except FailClosedError as exc:
        print(f"[restore:{PILLAR}] FALLO: {exc}", file=sys.stderr)
        return 1
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
