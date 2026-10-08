"""Copia verificada de objetos entre dos backends S3 (MinIO -> Garage).

Las URIs guardadas en la BD son `minio://<bucket>/<clave>` y NO cambian: el
esquema es solo un nombre historico, asi que no hay que reescribir filas. Lo
unico que se mueve son los bytes, con la misma clave y el mismo bucket.

Garantias:
  * Solo LEE del origen; nunca borra ni modifica nada en MinIO (rollback = no
    hacer nada: MinIO queda intacto).
  * Idempotente: un objeto ya presente en destino con mismo tamano y sha256 se
    salta. Se puede relanzar tras un corte.
  * Cada objeto copiado se RELEE del destino y se compara sha256 con el origen.
  * Sale con codigo != 0 si algo falta o difiere (fail-closed).

Uso (desde data-engine/, con las dos credenciales por entorno):
    SRC_ACCESS_KEY=... SRC_SECRET_KEY=... DST_ACCESS_KEY=... DST_SECRET_KEY=... \\
    python -m scripts.storage.migrate_minio_to_garage \\
        --src-endpoint minio:9000 --dst-endpoint garage:3900 --dst-region garage \\
        --bucket research [--dry-run] [--verify-only] --report /tmp/migracion.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from io import BytesIO
from typing import Any


def build_client(endpoint: str, access_key: str, secret_key: str, region: str = ""):
    from minio import Minio

    secure = endpoint.startswith("https://")
    host = endpoint.replace("https://", "").replace("http://", "").strip("/")
    return Minio(
        host,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=region or None,
    )


def _read(client, bucket: str, key: str) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def migrate(
    src,
    dst,
    bucket: str,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> dict[str, Any]:
    """Copia/verifica `bucket` de `src` a `dst` y devuelve el informe."""
    report: dict[str, Any] = {
        "bucket": bucket,
        "dry_run": dry_run,
        "verify_only": verify_only,
        "copied": [],
        "skipped": [],
        "missing": [],
        "mismatch": [],
        "errors": [],
        "bytes_copied": 0,
    }
    if not src.bucket_exists(bucket):
        report["errors"].append(f"el bucket origen '{bucket}' no existe")
        return report
    if not dry_run and not verify_only and not dst.bucket_exists(bucket):
        dst.make_bucket(bucket)

    for item in src.list_objects(bucket, recursive=True):
        key = item.object_name
        if key.endswith("/"):
            continue
        try:
            payload = _read(src, bucket, key)
            if len(payload) != item.size:
                report["errors"].append(
                    f"{key}: {len(payload)} bytes leidos, el listado decia {item.size}"
                )
                continue
            digest = _sha(payload)
            present = False
            try:
                present = _sha(_read(dst, bucket, key)) == digest
            except Exception:  # noqa: BLE001 - ausente o ilegible en destino
                present = False
            if present:
                report["skipped"].append(key)
                continue
            if verify_only or dry_run:
                (report["missing"] if verify_only else report["copied"]).append(key)
                continue
            content_type = getattr(src.stat_object(bucket, key), "content_type", None)
            dst.put_object(
                bucket,
                key,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type or "application/octet-stream",
            )
            if _sha(_read(dst, bucket, key)) != digest:
                report["mismatch"].append(key)
                continue
            report["copied"].append(key)
            report["bytes_copied"] += len(payload)
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue
            report["errors"].append(f"{key}: {type(exc).__name__}: {exc}")

    report["ok"] = not (report["errors"] or report["mismatch"] or report["missing"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src-endpoint", required=True)
    parser.add_argument("--dst-endpoint", required=True)
    parser.add_argument("--src-region", default="")
    parser.add_argument("--dst-region", default="garage")
    parser.add_argument("--bucket", default="research")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    try:
        src = build_client(
            args.src_endpoint, os.environ["SRC_ACCESS_KEY"], os.environ["SRC_SECRET_KEY"], args.src_region
        )
        dst = build_client(
            args.dst_endpoint, os.environ["DST_ACCESS_KEY"], os.environ["DST_SECRET_KEY"], args.dst_region
        )
    except KeyError as exc:
        print(f"falta la variable {exc.args[0]}", file=sys.stderr)
        return 2

    report = migrate(src, dst, args.bucket, dry_run=args.dry_run, verify_only=args.verify_only)
    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}
    print(json.dumps(summary, ensure_ascii=False))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if report.get("ok", False) or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
