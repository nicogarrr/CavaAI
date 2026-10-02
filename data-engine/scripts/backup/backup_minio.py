"""Backup VERIFICADO de MinIO a nivel de OBJETO, con versionado de bucket.

Un `tar` del volumen de MinIO no es un backup: solo se restaura en la misma
maquina, contra el mismo `/data` y con el mismo `.minio.sys`. Aqui se copia
objeto a objeto, direccionado por clave, de modo que un objeto subido hace una
hora se recupera en un bucket vacio de otra maquina.

El versionado de bucket se ACTIVA (idempotente) antes de copiar y se comprueba
despues: sin el, "recupera el objeto que se sobreescribio hace una hora" es
imposible porque la version anterior ya no existe en ningun sitio. El repo no
lo activaba (app/services/document_store.py hace `make_bucket` y nada mas), asi
que el manifiesto declara el estado real y el runbook avisa de la ventana previa
al primer backup con versionado.

Dos transportes, ambos con version declarada en el manifiesto:
  * `sdk` (por defecto): el cliente `minio`, que ya es dependencia fijada del
    data-engine (`minio>=7.2.7,<8`). No depende de que el host tenga `mc`.
  * `mc`: `mc mirror` + `mc version enable`, para cuando la copia sale a un
    bucket remoto con `mc` ya configurado (`--mc-alias`).

Uso:
    python -m scripts.backup.backup_minio --out backups/<id> \\
        --endpoint 127.0.0.1:9002 --bucket research
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    MINIO_IMAGE,
    MINIO_SDK_REQUIREMENT,
    MINIO_SERVER_RELEASE,
    Artifact,
    FailClosedError,
    ManifestBuilder,
    exit_with,
    minio_endpoint_config,
    redact,
    require,
    require_tool,
    run,
    sha256_bytes,
    sha256_file,
    tar_directory,
    tool_version,
)

PILLAR = "minio"
ARCHIVE_RELPATH = "minio/objects.tar.gz"
ARCHIVE_FORMAT = "minio_object_archive_targz"


def build_client(endpoint: str, access_key: str, secret_key: str):
    """Cliente MinIO con el mismo criterio de endpoint que document_store.py."""
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover - dependencia declarada
        raise FailClosedError(
            f"falta el SDK de MinIO ({MINIO_SDK_REQUIREMENT}); no se puede respaldar"
        ) from exc
    host, secure = minio_endpoint_config(endpoint)
    return Minio(endpoint=host, access_key=access_key, secret_key=secret_key, secure=secure)


def ensure_versioning(client, bucket: str) -> str:
    """Activa el versionado si hace falta y devuelve el estado real comprobado."""
    from minio.versioningconfig import ENABLED, VersioningConfig

    if not client.bucket_exists(bucket):
        raise FailClosedError(
            f"el bucket '{bucket}' no existe: un backup de un bucket inexistente es un "
            "backup vacio que el restore no puede distinguir de un fallo"
        )
    state = client.get_bucket_versioning(bucket)
    current = getattr(state, "status", None) or "Off"
    if current == "Enabled":
        return "Enabled"
    client.set_bucket_versioning(bucket, VersioningConfig(ENABLED))
    confirmed = getattr(client.get_bucket_versioning(bucket), "status", None) or "Off"
    require(
        confirmed == "Enabled",
        f"no se pudo activar el versionado en '{bucket}' (estado tras la llamada: "
        f"{confirmed}); sin el, una version sobrescrita se pierde para siempre",
    )
    return "Enabled (activado por este backup)"


def _stage_objects(
    client,
    bucket: str,
    staging: Path,
    *,
    include_versions: bool,
) -> list[dict[str, Any]]:
    """Descarga los objetos a un directorio temporal y describe cada uno.

    Con `include_versions` se copian TODAS las versiones (clave + version_id),
    que es lo unico que permite recuperar una version ya sobrescrita si el
    bucket de origen no esta disponible.
    """
    entries: list[dict[str, Any]] = []
    for item in client.list_objects(bucket, recursive=True, include_version=include_versions):
        if item.object_name.endswith("/"):
            continue
        relative = Path(*item.object_name.split("/"))
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            f"clave de objeto con traversal de ruta: {item.object_name!r}",
        )
        version_id = getattr(item, "version_id", None)
        suffix = "" if not version_id else f".{version_id}"
        target = staging / f"{relative.as_posix()}{suffix}"
        require(
            len(target.relative_to(staging).parts) == len(Path(*item.object_name.split("/")).parts),
            f"la version de '{item.object_name}' sale del directorio de staging",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        response = None
        try:
            response = client.get_object(bucket, item.object_name, version_id=version_id)
            payload = response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()
        require(
            len(payload) == item.size,
            f"{item.object_name}: {len(payload)} bytes leidos, el listado anunciaba {item.size}",
        )
        target.write_bytes(payload)
        entries.append(
            {
                "key": item.object_name,
                "archive_path": target.relative_to(staging).as_posix(),
                "bytes": item.size,
                "sha256": sha256_bytes(payload),
                "etag": (item.etag or "").strip('"'),
                "version_id": version_id or "",
                "last_modified": item.last_modified.isoformat() if item.last_modified else None,
            }
        )
    require(
        bool(entries),
        f"el bucket '{bucket}' no devolvio ningun objeto: no se respalda un bucket "
        "vacio (un fallo de credenciales o de endpoint se lee igual que un bucket limpio)",
    )
    return entries


def mc_mirror(
    *,
    alias: str,
    target_bucket: str,
    source_bucket: str,
    source_endpoint: str,
    access_key: str,
    secret_key: str,
) -> dict[str, Any]:
    """Copia fuera de maquina con `mc mirror` (opcional, --transport mc)."""
    binary = require_tool("mc", what="copia mc mirror")
    run([binary, "alias", "set", alias, source_endpoint, access_key, secret_key], what="mc alias set")
    run([binary, "mb", "--ignore-existing", f"{alias}/{target_bucket}"], what="mc mb")
    run(
        [binary, "mirror", "--overwrite", f"{alias}/{source_bucket}", f"{alias}/{target_bucket}"],
        timeout=3600,
        what="mc mirror",
    )
    listing = run(
        [binary, "ls", "--recursive", f"{alias}/{target_bucket}"],
        timeout=600,
        what="mc ls",
    )
    return {
        "mirror_objects": len([line for line in listing.stdout.splitlines() if line.strip()]),
        "mirror_target": f"{alias}/{target_bucket}",
    }


def sdk_transport_version() -> str:
    from importlib import metadata

    try:
        return metadata.version("minio")
    except metadata.PackageNotFoundError:  # pragma: no cover - solo sin instalar
        return "unknown"


def run_backup(
    backup_dir: Path,
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    backup_kind: str = "full",
    transport: str = "sdk",
    mc_alias: str | None = None,
    mc_target_bucket: str | None = None,
    enable_versioning: bool = True,
    include_versions: bool = False,
) -> ManifestBuilder:
    """Ejecuta el backup de MinIO y devuelve el ManifestBuilder con su parte."""
    backup_dir = backup_dir.resolve()
    client = build_client(endpoint, access_key, secret_key)
    versioning = ensure_versioning(client, bucket) if enable_versioning else "no gestionado"

    staging = backup_dir / "minio" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        entries = _stage_objects(client, bucket, staging, include_versions=include_versions)
        archive_path = backup_dir / ARCHIVE_RELPATH
        tar_directory(staging, archive_path)
    finally:
        # El tar es el artefacto; el staging son bytes duplicados en disco.
        import shutil

        shutil.rmtree(staging, ignore_errors=True)

    builder = ManifestBuilder(backup_dir=backup_dir, backup_kind=backup_kind)
    extra: dict[str, Any] = {
        "mode": transport,
        "image": MINIO_IMAGE,
        "server_release": MINIO_SERVER_RELEASE,
        "sdk_requirement": MINIO_SDK_REQUIREMENT,
    }
    if transport == "mc":
        require(
            bool(mc_alias and mc_target_bucket),
            "transporte mc sin --mc-alias/--mc-target-bucket: no hay destino para el mirror",
        )
        host, _ = minio_endpoint_config(endpoint)
        extra.update(
            mc_mirror(
                alias=str(mc_alias),
                target_bucket=str(mc_target_bucket),
                source_bucket=bucket,
                source_endpoint=f"http://{host}",
                access_key=access_key,
                secret_key=secret_key,
            )
        )
        version = tool_version([require_tool("mc", what="mc --version")])
    else:
        version = sdk_transport_version()
    builder.add_tool("minio", version, **extra)

    builder.add_artifact(
        Artifact(
            pillar=PILLAR,
            path=ARCHIVE_RELPATH,
            format=ARCHIVE_FORMAT,
            sha256=sha256_file(archive_path),
            bytes=archive_path.stat().st_size,
            kind=backup_kind,
            detail=f"bucket={bucket} objetos={len(entries)} (sha256 por clave en minio.objects)",
        )
    )

    builder.declare_minio(
        source_bucket=bucket,
        endpoint=endpoint,
        transport=transport,
        transport_version=version,
        versioning=versioning,
        versions_captured="all" if include_versions else "latest",
        object_count=len(entries),
        total_bytes=sum(entry["bytes"] for entry in entries),
        archive_path=ARCHIVE_RELPATH,
        objects=entries,
    )
    return builder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup verificado de MinIO (por objeto).")
    parser.add_argument("--out", required=True, help="Directorio de backup.")
    parser.add_argument("--endpoint", default="127.0.0.1:9002", help="host:port de MinIO.")
    parser.add_argument("--access-key", default="portfolio")
    parser.add_argument("--secret-key", default="portfoliosecret")
    parser.add_argument("--bucket", default="research")
    parser.add_argument("--kind", choices=("full", "incremental"), default="full")
    parser.add_argument("--transport", choices=("sdk", "mc"), default="sdk")
    parser.add_argument("--mc-alias", default=None, help="Alias de `mc` para la copia fuera.")
    parser.add_argument("--mc-target-bucket", default=None)
    parser.add_argument(
        "--no-enable-versioning",
        action="store_true",
        help="No activar el versionado del bucket (queda constancia en el manifiesto).",
    )
    parser.add_argument(
        "--include-versions",
        action="store_true",
        help="Copiar TODAS las versiones del bucket, no solo la ultima de cada clave.",
    )
    parser.add_argument("--fragment-out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        builder = run_backup(
            Path(args.out),
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            bucket=args.bucket,
            backup_kind=args.kind,
            transport=args.transport,
            mc_alias=args.mc_alias,
            mc_target_bucket=args.mc_target_bucket,
            enable_versioning=not args.no_enable_versioning,
            include_versions=args.include_versions,
        )
    except FailClosedError as exc:
        return exit_with(f"[backup:{PILLAR}] FALLO: {exc}", False)
    except Exception as exc:  # noqa: BLE001 - el SDK de MinIO levanta excepciones propias
        return exit_with(f"[backup:{PILLAR}] FALLO: {type(exc).__name__}: {redact(str(exc))}", False)

    lines = [
        f"[backup:{PILLAR}] ok: {builder.minio.get('object_count', 0)} objetos, "
        f"versionado={builder.minio.get('versioning')}, "
        f"versiones={builder.minio.get('versions_captured')}"
    ]
    if args.fragment_out:
        Path(args.fragment_out).write_text(
            json.dumps(
                {
                    "tools": builder.tools,
                    "artifacts": [a.as_dict() for a in builder.artifacts],
                    "minio": builder.minio,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return exit_with("\n".join(lines), True)


if __name__ == "__main__":
    raise SystemExit(main())
