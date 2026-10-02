"""Backup de los TRES pilares con UN solo manifiesto.

`manifest.json` es el contrato entre el backup y el restore: backup_id, version
del esquema (Alembic), herramientas y sus versiones, SHA-256 y tamano de cada
artefacto, y si cada artefacto es completo o incremental. Sin esto, un restore
es arqueologia.

Se ejecuta un pilar y el siguiente. Si uno falla, el backup falla: no se
escribe manifiesto parcial, porque un manifiesto que solo cubre Postgres es
indistinguible de un backup completo a medio hacer.

Uso:
    python -m scripts.backup.backup_all --out backups/20261002T101500Z
    python -m scripts.backup.backup_all --out-dir backups        # crea el backup_id
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup import backup_minio, backup_postgres, backup_qdrant  # noqa: E402
from scripts.backup._kit import (  # noqa: E402
    MANIFEST_FILENAME,
    FailClosedError,
    ManifestBuilder,
    new_backup_id,
    require,
)


def run_all(args: argparse.Namespace) -> tuple[ManifestBuilder, Path]:
    """Ejecuta los tres pilares y devuelve el builder con el backup ya escrito."""
    backup_id = args.backup_id or new_backup_id()
    backup_dir = Path(args.out) if args.out else Path(args.out_dir) / backup_id
    require(
        not (backup_dir / MANIFEST_FILENAME).exists(),
        f"{backup_dir} ya tiene un manifiesto: elige otro backup_id o borra el "
        "directorio. Un backup sobrescrito no se puede auditar",
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"[backup] destino: {backup_dir}")

    print("[backup] 1/3 postgres…")
    postgres = backup_postgres.run_backup(
        backup_dir,
        database=args.pg_database,
        user=args.pg_user,
        mode=args.pg_mode,
        container=args.pg_container,
        host=args.pg_host,
        port=args.pg_port,
        password=args.pg_password,
        backup_kind=args.kind,
        with_globals=not args.pg_no_globals,
        allow_schema_drift=args.allow_schema_drift,
    )
    print("[backup] 2/3 minio…")
    minio = backup_minio.run_backup(
        backup_dir,
        endpoint=args.minio_endpoint,
        access_key=args.minio_access_key,
        secret_key=args.minio_secret_key,
        bucket=args.minio_bucket,
        backup_kind=args.kind,
        transport=args.minio_transport,
        mc_alias=args.mc_alias,
        mc_target_bucket=args.mc_target_bucket,
        enable_versioning=not args.minio_no_versioning,
        include_versions=args.minio_include_versions,
    )
    print("[backup] 3/3 qdrant…")
    qdrant = backup_qdrant.run_backup(
        backup_dir,
        url=args.qdrant_url,
        api_key=args.qdrant_api_key,
        collections=args.qdrant_collection,
        backup_kind=args.kind,
    )

    builder = ManifestBuilder(
        backup_dir=backup_dir,
        backup_kind=args.kind,
        backup_id=backup_id,
        versions_dir=args.versions_dir,
    )
    for tool_name, entry in {**postgres.tools, **minio.tools, **qdrant.tools}.items():
        # `version` viaja como argumento posicional; el resto del detalle del
        # pilar (modo, imagen, sdk...) se copia sin repetir la clave.
        detail = {key: value for key, value in entry.items() if key != "version"}
        builder.add_tool(tool_name, str(entry["version"]), **detail)
    for pillar in (postgres, minio, qdrant):
        for artifact in pillar.artifacts:
            builder.add_artifact(artifact)
    builder.declare_postgres(**postgres.postgres)
    builder.declare_minio(**minio.minio)
    builder.declare_qdrant(**qdrant.qdrant)
    if args.kind == "incremental":
        builder.notes.append(
            "kind=incremental: este backup se declara incremental y por eso NO es "
            "restaurable por si solo. Necesita el backup 'full' que lo precede; el "
            "restore lo exige como --base-manifest."
        )
    return builder, backup_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup verificado de los tres pilares.")
    parser.add_argument("--out", default=None, help="Directorio exacto del backup.")
    parser.add_argument("--out-dir", default="backups", help="Directorio padre si no hay --out.")
    parser.add_argument("--backup-id", default=None, help="Id del backup (por defecto, ahora en UTC).")
    parser.add_argument("--kind", choices=("full", "incremental"), default="full")
    parser.add_argument(
        "--versions-dir",
        default=None,
        help="Directorio de migraciones Alembic (por defecto data-engine/alembic/versions).",
    )
    parser.add_argument("--allow-schema-drift", action="store_true")

    group = parser.add_argument_group("postgres")
    group.add_argument("--pg-database", default="cavaai_research")
    group.add_argument("--pg-user", default="portfolio")
    group.add_argument("--pg-mode", choices=("auto", "docker", "local"), default="auto")
    group.add_argument("--pg-container", default=None)
    group.add_argument("--pg-host", default=None)
    group.add_argument("--pg-port", type=int, default=None)
    group.add_argument("--pg-password", default=None)
    group.add_argument("--pg-no-globals", action="store_true")

    group = parser.add_argument_group("minio")
    group.add_argument("--minio-endpoint", default="127.0.0.1:9002")
    group.add_argument("--minio-access-key", default="portfolio")
    group.add_argument("--minio-secret-key", default="portfoliosecret")
    group.add_argument("--minio-bucket", default="research")
    group.add_argument("--minio-transport", choices=("sdk", "mc"), default="sdk")
    group.add_argument("--minio-no-versioning", action="store_true")
    group.add_argument("--minio-include-versions", action="store_true")
    group.add_argument("--mc-alias", default=None)
    group.add_argument("--mc-target-bucket", default=None)

    group = parser.add_argument_group("qdrant")
    group.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    group.add_argument("--qdrant-api-key", default=None)
    group.add_argument("--qdrant-collection", action="append", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.out and not args.out_dir:
        print("FALLO: falta --out o --out-dir", file=sys.stderr)
        return 1
    if args.versions_dir:
        args.versions_dir = Path(args.versions_dir)
    try:
        builder, backup_dir = run_all(args)
        manifest_path = builder.write()
    except FailClosedError as exc:
        print(f"[backup] FALLO: {exc}", file=sys.stderr)
        return 1
    print(f"[backup] completo: {manifest_path}")
    print(json.dumps({"backup_id": builder.backup_id, "dir": str(backup_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
