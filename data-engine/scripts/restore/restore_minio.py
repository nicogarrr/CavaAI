"""Restore DESTRUCTIVO de MinIO desde el backup, a un bucket limpio.

Un bucket destino VACIO es el caso de disaster recovery; por eso el restore
borra el bucket de destino (si existe) y lo vuelve a crear antes de subir, y
por eso exige `--confirm-restore`. Sobrescribir encima dejaría objetos del
destino que el backup no contiene y que, tras el restore, el verify_restore
contaria como desviación.

Cada objeto se sube con su SHA-256 verificado contra el manifiesto: el checksum
del `objects.tar.gz` protege el archivo entero, y este protege el mapping
clave -> contenido (un `.tar` bien formado puede llevar una clave cambiada).

Uso:
    python -m scripts.restore.restore_minio --manifest backups/<id> \\
        --endpoint 127.0.0.1:9002 --bucket research --confirm-restore
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    FailClosedError,
    artifacts_by_pillar,
    load_manifest,
    redact,
    require,
    sha256_file,
    untar_to,
    verify_artifact,
)
from scripts.backup.backup_minio import build_client  # noqa: E402

PILLAR = "minio"


def _recreate_bucket(client, bucket: str) -> None:
    """Bucket destino vacio: se borra y se vuelve a crear con el mismo nombre."""
    if client.bucket_exists(bucket):
        for item in client.list_objects(bucket, recursive=True, include_version=True):
            client.remove_object(bucket, item.object_name, version_id=getattr(item, "version_id", None))
        client.remove_bucket(bucket)
        print(f"[restore:{PILLAR}] bucket '{bucket}' vaciado (destino limpio)")
    client.make_bucket(bucket)
    print(f"[restore:{PILLAR}] bucket '{bucket}' creado vacio")


def run_restore(
    manifest_path: Path,
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str | None = None,
    enable_versioning: bool = True,
) -> dict:
    """Restaura el bucket desde el manifiesto y devuelve su informe."""
    manifest = load_manifest(manifest_path)
    backup_dir = manifest_path if manifest_path.is_dir() else manifest_path.parent
    artifacts = artifacts_by_pillar(manifest, PILLAR)
    require(bool(artifacts), f"el manifiesto no declara artefactos de '{PILLAR}'")
    for artifact in artifacts:
        verify_artifact(backup_dir, artifact)

    entries = list(manifest["minio"].get("objects") or [])
    require(bool(entries), "el manifiesto no declara objetos de MinIO: no hay nada que restaurar")

    target_bucket = bucket or str(manifest["minio"]["source_bucket"])
    client = build_client(endpoint, access_key, secret_key)
    _recreate_bucket(client, target_bucket)
    if enable_versioning:
        from minio.versioningconfig import ENABLED, VersioningConfig

        client.set_bucket_versioning(target_bucket, VersioningConfig(ENABLED))

    with tempfile.TemporaryDirectory(prefix="cavaai-restore-minio-") as tmp:
        staging = Path(tmp)
        extracted = untar_to(
            backup_dir / str(manifest["minio"]["archive_path"]),
            staging,
            what="restaurar objetos de MinIO",
        )
        require(
            extracted == len(entries),
            f"el tar contiene {extracted} ficheros y el manifiesto declara {len(entries)} objetos",
        )
        restored: list[str] = []
        for entry in entries:
            relative = Path(str(entry["archive_path"]))
            require(
                not relative.is_absolute() and ".." not in relative.parts,
                f"el manifiesto declara una ruta fuera del archivo: {entry['archive_path']!r}",
            )
            source = staging / relative
            require(source.is_file(), f"el archivo {entry['archive_path']} no esta en el tar")
            actual = sha256_file(source)
            require(
                actual == entry["sha256"],
                f"el objeto '{entry['key']}' tiene sha256 {actual} y el manifiesto "
                f"declara {entry['sha256']}: el archivo no corresponde a esa clave",
            )
            client.fput_object(target_bucket, str(entry["key"]), str(source))
            restored.append(str(entry["key"]))
    print(f"[restore:{PILLAR}] {len(restored)} objetos subidos a '{target_bucket}'")
    return {
        "pillar": PILLAR,
        "bucket": target_bucket,
        "endpoint": endpoint,
        "objects_restored": len(restored),
        "expected_objects": len(entries),
        "total_bytes": sum(int(entry["bytes"]) for entry in entries),
        "versioning": "Enabled" if enable_versioning else "Off",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore verificado de MinIO a bucket limpio.")
    parser.add_argument("--manifest", required=True, help="Directorio del backup o manifest.json.")
    parser.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Obligatorio: el restore vacia el bucket de destino.",
    )
    parser.add_argument("--endpoint", default="127.0.0.1:9002", help="host:port de MinIO destino.")
    parser.add_argument("--access-key", default="portfolio")
    parser.add_argument("--secret-key", default="portfoliosecret")
    parser.add_argument("--bucket", default=None, help="Bucket destino (por defecto, el del backup).")
    parser.add_argument(
        "--no-versioning",
        action="store_true",
        help="No activar el versionado en el bucket restaurado.",
    )
    parser.add_argument("--report-out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_restore:
        print("FALLO: falta --confirm-restore. El restore vacia el bucket de destino.", file=sys.stderr)
        return 1
    try:
        report = run_restore(
            Path(args.manifest),
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            bucket=args.bucket,
            enable_versioning=not args.no_versioning,
        )
    except FailClosedError as exc:
        print(f"[restore:{PILLAR}] FALLO: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - el SDK de MinIO lanza excepciones propias
        print(f"[restore:{PILLAR}] FALLO: {type(exc).__name__}: {redact(str(exc))}", file=sys.stderr)
        return 1
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
