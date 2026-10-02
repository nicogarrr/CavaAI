"""Backup VERIFICADO de Qdrant: snapshot POR COLECCION via la API HTTP.

Copiar el directorio de datos de Qdrant no es un backup: solo se restaura en la
misma maquina, con el mismo path de almacenamiento y sin pasar por la API. El
`POST /collections/{c}/snapshots` produce un `.snapshot` autocontenido que se
sube a OTRO servidor con `POST /collections/{c}/snapshots/upload` sin tocar
volumenes. Ese es el unico backup que sobrevive a perder la maquina.

Misma fuente de verdad que el RAG de la aplicacion (app/services/rag.py):
colecciones de `QdrantClient(url=settings.qdrant_url)` y, si algun dia se anade
API key al servicio, `--api-key` / `QDRANT_API_KEY`. El patron de autenticacion
es el del cliente, no uno inventado aqui.

Por que la API y no `curl`: `_kit` no depende de que el host tenga curl
instalado, el upload multipart es exacto y los errores se pueden distinguir
("coleccion vacia" de "Qdrant caido"), que es lo que necesita el fail-closed.

Uso:
    python -m scripts.backup.backup_qdrant --out backups/<id> --url http://127.0.0.1:6333
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    QDRANT_IMAGE,
    REQUIRED_QDRANT_MAJOR_MINOR,
    Artifact,
    FailClosedError,
    ManifestBuilder,
    exit_with,
    qdrant_base_url,
    redact,
    require,
    sha256_file,
)

PILLAR = "qdrant"
SNAPSHOT_FORMAT = "qdrant_collection_snapshot"
#: Cuanto se espera a que el snapshot pase a `completed` antes de rendirse.
SNAPSHOT_POLL_SECONDS = 120
SNAPSHOT_POLL_INTERVAL = 2


def _request(
    url: str,
    api_key: str | None,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 60,
    check: bool = True,
    what: str = "",
) -> Any:
    """Una llamada a la API de Qdrant. Falla con el motivo si no es `ok`."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - dependencia declarada
        raise FailClosedError("falta httpx; no se puede hablar con la API de Qdrant") from exc

    headers: dict[str, str] = {}
    if api_key:
        headers["api-key"] = api_key
    if content_type:
        headers["Content-Type"] = content_type
    label = what or f"{method} {url}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                content=content,
            )
    except Exception as exc:  # noqa: BLE001 - httpx lanza una familia entera
        raise FailClosedError(f"{label}: {type(exc).__name__}: {redact(str(exc))}") from exc

    if check and response.status_code >= 400:
        raise FailClosedError(
            f"{label}: HTTP {response.status_code}: {redact(response.text[:400])}"
        )
    return response


def _json_request(
    url: str,
    api_key: str | None,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    timeout: int = 60,
    what: str = "",
) -> dict[str, Any]:
    """Como `_request` pero exigiendo `status: ok` en el cuerpo.

    Un HTTP 200 con `status: error` es un fallo de Qdrant: el gate de RAG de
    ci.yml ya distingue esa situation en los tests, aqui se aplica igual.
    """
    response = _request(
        url, api_key, method=method, json_body=json_body, timeout=timeout, what=what
    )
    label = what or url
    try:
        payload = response.json()
    except ValueError as exc:
        raise FailClosedError(f"{label}: respuesta no es JSON ({exc})") from exc
    require(isinstance(payload, dict), f"{label}: el cuerpo no es un objeto JSON")
    status = payload.get("status")
    require(
        status == "ok",
        f"{label}: status={status!r} result={payload.get('result')!r}",
    )
    return payload


def server_version(base_url: str, api_key: str | None) -> str:
    """Version del servidor, leida de `GET /`.

    A diferencia del resto de endpoints, la raiz de Qdrant NO envuelve la
    respuesta en `{status, result}`: devuelve `{title, version, commit}` plano.
    """
    response = _request(f"{base_url}/", api_key, timeout=60, what="Qdrant version")
    try:
        payload = response.json()
    except ValueError as exc:
        raise FailClosedError(f"Qdrant version: respuesta no JSON en {base_url}/ ({exc})") from exc
    require(isinstance(payload, dict), f"Qdrant version: cuerpo inesperado en {base_url}/")
    version = str(payload.get("version") or "unknown")
    require(
        version.startswith(REQUIRED_QDRANT_MAJOR_MINOR),
        f"Qdrant {version} != pin {QDRANT_IMAGE} ({REQUIRED_QDRANT_MAJOR_MINOR}): "
        "un snapshot de otra version mayor no se restaura fiablemente",
    )
    return version


def list_collections(base_url: str, api_key: str | None) -> list[str]:
    payload = _json_request(f"{base_url}/collections", api_key, what="listar colecciones")
    names = [entry["name"] for entry in payload["result"]["collections"]]
    require(
        bool(names),
        "Qdrant no tiene colecciones: un backup sin colecciones es un backup vacio "
        "(comprueba la URL: apuntar al puerto equivocado responde igual de vacio)",
    )
    return sorted(names)


def vector_dimensions(vectors: Any) -> dict[str, int]:
    """Normaliza `config.params.vectors` a `{nombre: dimension}`.

    Qdrant devuelve tres formas segun la coleccion, y confundirlas daria
    dimensiones vacias o un `AttributeError` al comparar el restore:
      * vector sin nombre: `{"size": 384, "distance": "Cosine"}` (lo que usa el
        RAG de la app, app/services/rag.py).
      * vectores con nombre: `{"texto": {"size": 384, ...}, ...}`.
      * lista (formato antiguo): `[{"name": "texto", "size": 384}, ...]`.
    """
    if isinstance(vectors, list):
        return {
            str(entry.get("name", "")): int(entry.get("size", 0))
            for entry in vectors
            if isinstance(entry, dict)
        }
    if isinstance(vectors, dict):
        if isinstance(vectors.get("size"), int):
            return {"": int(vectors["size"])}
        return {
            str(name): int(params.get("size", 0))
            for name, params in vectors.items()
            if isinstance(params, dict)
        }
    return {}


def collection_info(base_url: str, api_key: str | None, collection: str) -> dict[str, Any]:
    payload = _json_request(
        f"{base_url}/collections/{collection}", api_key, what=f"info de {collection}"
    )
    result = payload["result"]
    dimensions = vector_dimensions(result.get("config", {}).get("params", {}).get("vectors"))
    require(
        bool(dimensions),
        f"coleccion {collection}: Qdrant no declara dimensiones "
        f"({result.get('config', {}).get('params', {}).get('vectors')!r})",
    )
    return {
        "name": collection,
        "points": int(result.get("points_count", 0)),
        "vectors_count": result.get("indexed_vectors_count"),
        "status": result.get("status"),
        "dimensions": dimensions,
    }


def sample_point_id(base_url: str, api_key: str | None, collection: str) -> str | None:
    """Primer id de punto, para comprobar que un hit concreto se recupera."""
    payload = _json_request(
        f"{base_url}/collections/{collection}/points/scroll",
        api_key,
        method="POST",
        json_body={"limit": 1, "with_payload": False, "with_vector": False},
        what=f"scroll de {collection}",
    )
    points = payload["result"].get("points") or []
    if not points:
        return None
    point_id = points[0].get("id")
    return None if point_id is None else str(point_id)


def snapshot_collection(
    base_url: str,
    api_key: str | None,
    collection: str,
    target: Path,
    *,
    poll_seconds: int = SNAPSHOT_POLL_SECONDS,
) -> dict[str, Any]:
    """Crea el snapshot, espera a que exista y lo descarga.

    `GET /collections/{c}/snapshots` no expone `state`: un snapshot aparece en
    el listado cuando ya esta escrito. Se espera a que aparezca y, si no,
    FALLA (fail-closed): descargar a medias produciria un artefacto corrupto
    que el restore no detectaria hasta mas tarde.

    El `checksum` que devuelve Qdrant es el SHA-256 del `.snapshot`, calculado
    por el servidor: cuando viene en hex de 64 se COMPRUEBA contra el fichero
    descargado. Es una verificacion de integridad independiente de la nuestra
    (el digest no lo calculamos nosotros), asi que detecta una descarga
    truncada o alterada antes de escribir el manifiesto.
    """
    created = _json_request(
        f"{base_url}/collections/{collection}/snapshots",
        api_key,
        method="POST",
        what=f"crear snapshot de {collection}",
    )
    name = str(created["result"]["name"])
    deadline = time.monotonic() + poll_seconds
    entry: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        listing = _json_request(
            f"{base_url}/collections/{collection}/snapshots",
            api_key,
            what=f"listar snapshots de {collection}",
        )
        entry = next((item for item in listing["result"] if item.get("name") == name), None)
        if entry is not None:
            break
        time.sleep(SNAPSHOT_POLL_INTERVAL)
    require(
        entry is not None,
        f"el snapshot '{name}' de {collection} no aparece en el listado en {poll_seconds}s: "
        "no se descarga a ciegas un artefacto que puede estar a medias",
    )
    response = _request(
        f"{base_url}/collections/{collection}/snapshots/{name}",
        api_key,
        timeout=1800,
        what=f"descargar snapshot de {collection}",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    require(target.stat().st_size > 0, f"snapshot de {collection} descargado vacio")
    digest = sha256_file(target)
    server_checksum = str(entry.get("checksum") or "")
    if len(server_checksum) == 64:
        require(
            server_checksum == digest,
            f"snapshot de {collection}: Qdrant declara el checksum {server_checksum} y el "
            f"fichero descargado hashea {digest} (descarga alterada o truncada)",
        )
    if entry.get("size"):
        require(
            target.stat().st_size == int(entry["size"]),
            f"snapshot de {collection}: {target.stat().st_size} bytes descargados, "
            f"Qdrant anuncia {entry['size']} (descarga truncada)",
        )
    return {
        "snapshot_name": name,
        "qdrant_checksum": server_checksum,
        "snapshot_sha256": digest,
        "bytes": target.stat().st_size,
    }


def run_backup(
    backup_dir: Path,
    *,
    url: str,
    api_key: str | None = None,
    collections: list[str] | None = None,
    backup_kind: str = "full",
) -> ManifestBuilder:
    """Ejecuta el backup de Qdrant y devuelve el ManifestBuilder con su parte."""
    base_url = qdrant_base_url(url)
    version = server_version(base_url, api_key)
    selected = collections or list_collections(base_url, api_key)
    require(
        bool(selected),
        "lista de colecciones vacia: no se respalda un Qdrant sin indice",
    )

    builder = ManifestBuilder(backup_dir=backup_dir, backup_kind=backup_kind)
    builder.add_tool(
        "qdrant",
        version,
        mode="http-api",
        image=QDRANT_IMAGE,
        url=base_url,
        endpoints=["POST /collections/{c}/snapshots", "GET /collections/{c}/snapshots/{name}"],
    )

    described: list[dict[str, Any]] = []
    for collection in selected:
        info = collection_info(base_url, api_key, collection)
        relative = f"qdrant/{collection}.snapshot"
        snapshot = snapshot_collection(base_url, api_key, collection, backup_dir / relative)
        artifact_path = backup_dir / relative
        builder.add_artifact(
            Artifact(
                pillar=PILLAR,
                path=relative,
                format=SNAPSHOT_FORMAT,
                sha256=sha256_file(artifact_path),
                bytes=artifact_path.stat().st_size,
                kind=backup_kind,
                detail=f"coleccion={collection} snapshot={snapshot['snapshot_name']}",
            )
        )
        described.append(
            {
                **info,
                **snapshot,
                "sample_point_id": sample_point_id(base_url, api_key, collection),
                "artifact": relative,
            }
        )

    builder.declare_qdrant(
        url=base_url,
        server_version=version,
        collection_count=len(described),
        total_points=sum(entry["points"] for entry in described),
        collections=described,
    )
    return builder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup verificado de Qdrant (snapshots).")
    parser.add_argument("--out", required=True, help="Directorio de backup.")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:6333",
        help="API de Qdrant; el mismo valor que QDRANT_URL de la aplicacion.",
    )
    parser.add_argument("--api-key", default=None, help="Cabecera api-key, si Qdrant la exige.")
    parser.add_argument(
        "--collection",
        action="append",
        default=None,
        help="Coleccion concreta (repetible). Por defecto, todas las que existan.",
    )
    parser.add_argument("--kind", choices=("full", "incremental"), default="full")
    parser.add_argument("--fragment-out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        builder = run_backup(
            Path(args.out),
            url=args.url,
            api_key=args.api_key,
            collections=args.collection,
            backup_kind=args.kind,
        )
    except FailClosedError as exc:
        return exit_with(f"[backup:{PILLAR}] FALLO: {exc}", False)

    lines = [
        f"[backup:{PILLAR}] ok: {builder.qdrant.get('collection_count', 0)} colecciones, "
        f"{builder.qdrant.get('total_points', 0)} puntos, "
        f"servidor={builder.qdrant.get('server_version')}"
    ]
    if args.fragment_out:
        Path(args.fragment_out).write_text(
            json.dumps(
                {
                    "tools": builder.tools,
                    "artifacts": [a.as_dict() for a in builder.artifacts],
                    "qdrant": builder.qdrant,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return exit_with("\n".join(lines), True)


if __name__ == "__main__":
    raise SystemExit(main())
