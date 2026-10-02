"""Restore DESTRUCTIVO de Qdrant desde el backup, a colecciones limpias.

Se usa EXCLUSIVAMENTE la API (`POST /collections/{c}/snapshots/upload`): asi el
mismo backup restaura en otra maquina, en otro contenedor y en otro volumen, sin
copiar ficheros de datos a mano. Por eso se BORRAN antes las colecciones
destino (un snapshot subido sobre una coleccion con puntos mezclaria los
indices viejo y nuevo); si el borrado falla, no se sube nada.

`upload` crea la coleccion si no existe y la reemplaza si existe, asi que un
fallo de subida deja el estado anterior intacto.

Uso:
    python -m scripts.restore.restore_qdrant --manifest backups/<id> \\
        --url http://127.0.0.1:6333 --confirm-restore
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    FailClosedError,
    artifacts_by_pillar,
    load_manifest,
    redact,
    require,
    verify_artifact,
)
from scripts.backup.backup_qdrant import _json_request, _request, collection_info  # noqa: E402

PILLAR = "qdrant"


def upload_snapshot(
    base_url: str,
    api_key: str | None,
    collection: str,
    snapshot_path: Path,
) -> None:
    """Sube un `.snapshot` con multipart. HTTP 200 no basta: se exige result=true."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - dependencia declarada
        raise FailClosedError("falta httpx; no se puede hablar con la API de Qdrant") from exc
    headers = {"api-key": api_key} if api_key else {}
    with snapshot_path.open("rb") as handle:
        try:
            with httpx.Client(timeout=1800) as client:
                response = client.post(
                    f"{base_url}/collections/{collection}/snapshots/upload?priority=snapshot",
                    headers=headers,
                    files={"snapshot": (snapshot_path.name, handle, "application/octet-stream")},
                )
        except Exception as exc:  # noqa: BLE001 - httpx lanza una familia entera
            raise FailClosedError(
                f"subir snapshot de {collection}: {type(exc).__name__}: {redact(str(exc))}"
            ) from exc
    require(
        response.status_code < 400,
        f"subir snapshot de {collection}: HTTP {response.status_code}: {redact(response.text[:400])}",
    )
    payload = response.json()
    require(
        payload.get("status") == "ok" and payload.get("result") is True,
        f"subir snapshot de {collection}: {payload.get('status')!r}/{payload.get('result')!r}",
    )


def run_restore(
    manifest_path: Path,
    *,
    url: str,
    api_key: str | None = None,
    delete_before_upload: bool = True,
) -> dict:
    """Restaura las colecciones desde el manifiesto y devuelve su informe."""
    manifest = load_manifest(manifest_path)
    backup_dir = manifest_path if manifest_path.is_dir() else manifest_path.parent
    artifacts = artifacts_by_pillar(manifest, PILLAR)
    require(bool(artifacts), f"el manifiesto no declara artefactos de '{PILLAR}'")
    for artifact in artifacts:
        verify_artifact(backup_dir, artifact)

    collections = list(manifest["qdrant"].get("collections") or [])
    require(bool(collections), "el manifiesto no declara colecciones de Qdrant")

    base_url = url.rstrip("/")
    _json_request(f"{base_url}/collections", api_key, what="Qdrant alcanzable antes del restore")

    restored: list[dict] = []
    for entry in collections:
        name = str(entry["name"])
        artifact = next(
            (a for a in artifacts if a["path"].endswith(f"{name}.snapshot")),
            None,
        )
        require(
            artifact is not None,
            f"la coleccion '{name}' no tiene artefacto .snapshot en el manifiesto",
        )
        if delete_before_upload:
            # Destino limpio: si el borrado falla, el restore para aqui y no
            # sube un snapshot encima de una coleccion con datos de otro indice.
            _request(
                f"{base_url}/collections/{name}",
                api_key,
                method="DELETE",
                timeout=120,
                what=f"eliminar coleccion {name}",
                check=False,
            )
            print(f"[restore:{PILLAR}] coleccion '{name}' eliminada (destino limpio)")
        upload_snapshot(base_url, api_key, name, backup_dir / str(artifact["path"]))
        info = collection_info(base_url, api_key, name)
        restored.append(info)
        print(f"[restore:{PILLAR}] coleccion '{name}' restaurada ({info['points']} puntos)")

    return {
        "pillar": PILLAR,
        "url": base_url,
        "collections_restored": len(restored),
        "expected_collections": len(collections),
        "points_restored": sum(int(info["points"]) for info in restored),
        "expected_points": sum(int(entry["points"]) for entry in collections),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore verificado de Qdrant por la API.")
    parser.add_argument("--manifest", required=True, help="Directorio del backup o manifest.json.")
    parser.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Obligatorio: el restore elimina las colecciones de destino.",
    )
    parser.add_argument("--url", default="http://127.0.0.1:6333", help="API de Qdrant destino.")
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--keep-collections",
        action="store_true",
        help="No borrar antes de subir (mezcla el snapshot con lo que hubiera).",
    )
    parser.add_argument("--report-out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_restore:
        print(
            "FALLO: falta --confirm-restore. El restore elimina colecciones de destino.",
            file=sys.stderr,
        )
        return 1
    try:
        report = run_restore(
            Path(args.manifest),
            url=args.url,
            api_key=args.api_key,
            delete_before_upload=not args.keep_collections,
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
