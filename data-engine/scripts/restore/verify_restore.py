"""VERIFICACION del restore: que lo restaurado SIRVA, no que el comando saliera con 0.

Este es el modulo que separa "hice `pg_restore`" de "tengo una base recuperada".
Cada comprobacion compara el destino contra el MANIFIESTO del backup y ninguna
puede terminar en "omitido":

  (a) esquema   `pg_restore --list` del dump + `information_schema` del destino
                declaran todas las tablas del manifiesto.
  (b) conteos   `count(*)` por tabla debe coincidir EXACTAMENTE (desviacion 0).
  (c) esquema   `alembic_version` del destino == manifiesto == head del codigo.
                Un dump anterior al head restaura "bien" y rompe al arrancar.
  (d) aplicacion la app ARRANCA contra la base restaurada, responde al endpoint
                de salud y a uno de datos con un valor que estaba en el backup.
  (e) objetos   cada clave de MinIO es LEGIBLE y su sha256 es el del manifiesto
                (que el bucket exista no demuestra que sirvan datos).
  (f) vectores  la coleccion de Qdrant tiene los mismos puntos, las mismas
                dimensiones y devuelve el punto de ejemplo con el mismo id.

Fail-closed: si una comprobacion no se puede ejecutar (servicio caido,
herramienta ausente, `--app-base-url` no proporcionado) el resultado es FALLO
con su motivo. Es el mismo principio que el gate de RAG de ci.yml ("RAG
activation tests skipped -> exit 1").

Uso:
    python -m scripts.restore.verify_restore --manifest backups/<id> \\
        --pg-host 127.0.0.1 --app-base-url http://127.0.0.1:8000 \\
        --minio-endpoint 127.0.0.1:9002 --qdrant-url http://127.0.0.1:6333
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup._kit import (  # noqa: E402
    APP_DATA_LIMIT,
    APP_DATA_PATH,
    APP_PUBLIC_HEALTH_PATH,
    APP_READY_PATH,
    FailClosedError,
    PsqlTarget,
    alembic_head,
    artifacts_by_pillar,
    format_table,
    load_manifest,
    qdrant_base_url,
    redact,
    require,
    sha256_bytes,
)
from scripts.backup.backup_minio import build_client  # noqa: E402
from scripts.backup.backup_postgres import table_counts  # noqa: E402
from scripts.backup.backup_qdrant import _json_request, collection_info  # noqa: E402

REPORT_FILENAME = "verify_report.json"
VALID_CHECKS = ("a_esquema", "b_conteos", "c_alembic", "d_aplicacion", "e_objetos", "f_vectores")

#: Fases. Los conteos se comprueban ANTES de arrancar la aplicacion porque el
#: lifespan de la app INSERTA filas fuera de produccion: `main.py` llama a
#: `ensure_company_master()` y `configure_model_aliases()` cuando
#: `APP_ENV != production`. Con la app ya arrancada, `companies` pasa de 12 a
#: 35 y la comparacion contra el manifiesto daria un falso positivo ("el restore
#: perdio datos") o, peor, taparia una perdida real de filas.
PHASE_DATA = "data"
PHASE_APP = "app"
PHASE_ALL = "all"
PHASES = (PHASE_ALL, PHASE_DATA, PHASE_APP)
_CHECKS_BY_PHASE = {
    PHASE_DATA: ("a_esquema", "b_conteos", "c_alembic", "e_objetos", "f_vectores"),
    PHASE_APP: ("d_aplicacion",),
}


@dataclass(frozen=True)
class CheckResult:
    """Resultado de UNA comprobacion. No hay tercer estado: o pasa, o falla."""

    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def _run(name: str, body, *, required: str = "") -> CheckResult:
    """Ejecuta una comprobacion y convierte CUALQUIER problema en fallo con motivo.

    `required` es el nombre del servicio/endpoint que falto: sin el, el fallo se
    explica como "no se pudo comprobar" y no como "todo verde".
    """
    try:
        passed, detail = body()
    except FailClosedError as exc:
        return CheckResult(name, False, f"NO SE PUDO COMPROBAR{required and f' ({required})'}: {exc}")
    except Exception as exc:  # noqa: BLE001 - un error inesperado tambien es un fallo
        return CheckResult(name, False, f"ERROR{required and f' ({required})'}: {type(exc).__name__}: {exc}")
    return CheckResult(name, passed, detail)


# --- (a) esquema declarado y esquema real -----------------------------------


def check_schema(manifest: dict, backup_dir: Path, target: PsqlTarget) -> CheckResult:
    def body() -> tuple[bool, str]:
        from scripts.backup._kit import run
        from scripts.restore.restore_postgres import _stage_dump_into_container

        dump = next(
            a for a in artifacts_by_pillar(manifest, "postgres") if a["format"] == "pg_dump_custom"
        )
        dump_path = backup_dir / dump["path"]
        if target.mode == "docker":
            dump_argument = _stage_dump_into_container(str(target.container), dump_path)
        else:
            dump_argument = str(dump_path)
        listing = run(
            [*target.argv("pg_restore", "--list"), dump_argument],
            timeout=600,
            what="pg_restore --list",
        )
        declared_tables: set[str] = set()
        for line in listing.stdout.splitlines():
            if " TABLE " not in line or " TABLE DATA " in line:
                continue
            # Formato de `pg_restore --list`: "<oid>; <oid> <oid> TABLE <schema> <tabla> <owner>".
            fields = line.split(" TABLE ", 1)[1].split()
            if len(fields) >= 2:
                declared_tables.add(fields[1])
        missing_from_dump = sorted(set(manifest["postgres"]["tables"]) - declared_tables)
        require(
            not missing_from_dump,
            f"el dump no declara las tablas {missing_from_dump}",
        )
        live = {
            line.strip()
            for line in target.psql_value(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            ).splitlines()
            if line.strip()
        }
        missing = sorted(set(manifest["postgres"]["tables"]) - live)
        require(not missing, f"faltan tablas en la base restaurada: {missing}")
        return True, (
            f"{len(declared_tables)} tablas en el dump y {len(live)} en la base restaurada; "
            f"las {len(manifest['postgres']['tables'])} del manifiesto estan"
        )

    return _run("a_esquema", body, required="pg_restore/information_schema")


# --- (b) conteos exactos ----------------------------------------------------


def check_counts(manifest: dict, target: PsqlTarget) -> CheckResult:
    def body() -> tuple[bool, str]:
        expected: dict[str, int] = {str(k): int(v) for k, v in manifest["postgres"]["tables"].items()}
        require(bool(expected), "el manifiesto no declara conteos")
        actual = table_counts(target, tables=sorted(expected))
        drifted = [
            f"{table}: {actual.get(table)} != {expected[table]}"
            for table in sorted(expected)
            if actual.get(table) != expected[table]
        ]
        require(
            not drifted,
            f"{len(drifted)} tabla(s) con desviacion distinta de 0: {'; '.join(drifted[:5])}",
        )
        return True, f"{len(expected)} tablas con el conteo exacto del manifiesto (desviacion 0)"

    return _run("b_conteos", body, required="Postgres")


# --- (c) revision de Alembic ------------------------------------------------


def check_alembic(manifest: dict, admin: PsqlTarget, *, versions_dir: Path | None = None) -> CheckResult:
    def body() -> tuple[bool, str]:
        live = admin.psql_value("SELECT version_num FROM alembic_version")
        require(
            bool(live),
            "la base restaurada no tiene fila en alembic_version: no es una base migrada",
        )
        restored = live.splitlines()[0].strip()
        declared = str(manifest["postgres"]["alembic_version"])
        code_head = alembic_head(versions_dir)
        require(
            restored == declared,
            f"la base restaurada esta en {restored} y el manifiesto declara {declared}",
        )
        require(
            restored == code_head,
            f"la base restaurada esta en {restored} y el codigo en {code_head}: "
            "arrancaria con un esquema anterior al head",
        )
        return True, f"alembic_version restaurada={restored} = manifiesto = head del codigo"

    return _run("c_alembic", body, required="Postgres/alembic_version")


# --- (d) la aplicacion arranca y sirve datos -------------------------------


def check_app(manifest: dict, base_url: str, *, timeout: int = 30) -> CheckResult:
    def body() -> tuple[bool, str]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dependencia declarada
            raise FailClosedError("falta httpx para probar la aplicacion") from exc
        root = base_url.rstrip("/")
        require(bool(root), "--app-base-url vacio")
        problems: list[str] = []
        try:
            with httpx.Client(timeout=timeout) as client:
                ready = client.get(f"{root}{APP_READY_PATH}")
                public = client.get(f"{root}{APP_PUBLIC_HEALTH_PATH}")
                data = client.get(f"{root}{APP_DATA_PATH}", params={"limit": APP_DATA_LIMIT})
        except Exception as exc:  # noqa: BLE001 - httpx lanza una familia entera
            raise FailClosedError(
                f"la aplicacion no responde en {root}: {type(exc).__name__}: {redact(str(exc))}"
            ) from exc

        require(
            ready.status_code == 200,
            f"GET {APP_READY_PATH} devolvio HTTP {ready.status_code}: {ready.text[:200]}",
        )
        ready_checks = ready.json().get("checks", {})
        database_state = ready_checks.get("database")
        require(
            database_state == "ok",
            f"{APP_READY_PATH} reporta la base como {database_state!r}, no 'ok'",
        )
        for pillar, endpoint in (("qdrant", "qdrant"), ("minio", "minio")):
            state = ready_checks.get(endpoint)
            require(
                state == "ok",
                f"{APP_READY_PATH} reporta {pillar} como {state!r}: la app no esta "
                "conectada al pilar restaurado",
            )

        require(
            public.status_code == 200,
            f"GET {APP_PUBLIC_HEALTH_PATH} devolvio HTTP {public.status_code}",
        )
        public_body = public.json()
        require(
            public_body.get("status") == "ok",
            f"{APP_PUBLIC_HEALTH_PATH} responde status={public_body.get('status')!r} "
            f"(schema={public_body.get('schema')!r})",
        )
        require(
            not public_body.get("schema"),
            f"la app arranca pero con el esquema a medias: {public_body.get('schema')!r}",
        )

        require(
            data.status_code == 200,
            f"GET {APP_DATA_PATH} devolvio HTTP {data.status_code}: {data.text[:200]}",
        )
        rows = data.json()
        require(isinstance(rows, list), f"{APP_DATA_PATH} no devuelve una lista")
        expected_tickers = [str(v) for v in manifest["postgres"].get("probe_values") or []]
        if expected_tickers:
            column = str(manifest["postgres"].get("probe_column") or "ticker")
            served = {str(row.get(column)) for row in rows if isinstance(row, dict)}
            missing = [ticker for ticker in expected_tickers if ticker not in served]
            require(
                not missing,
                f"{APP_DATA_PATH} no devuelve {missing}, que estaban en el backup "
                f"(sirve {len(served)} filas distintas)",
            )
            problems.append(f"{len(expected_tickers)}/{len(expected_tickers)} tickers del backup servidos")
        else:
            problems.append("el backup no declara probe_values: solo se comprueba que la API responde")
        return True, f"ready.database=ok, schema=[] y {APP_DATA_PATH} responde ({'; '.join(problems)})"

    return _run("d_aplicacion", body, required="app en --app-base-url")


# --- (e) objetos de MinIO legibles por clave --------------------------------


def check_objects(manifest: dict, endpoint: str, access_key: str, secret_key: str) -> CheckResult:
    def body() -> tuple[bool, str]:
        expected = list(manifest["minio"].get("objects") or [])
        require(bool(expected), "el manifiesto no declara objetos de MinIO")
        client = build_client(endpoint, access_key, secret_key)
        bucket = str(manifest["minio"]["source_bucket"])
        require(
            client.bucket_exists(bucket),
            f"el bucket '{bucket}' no existe tras el restore",
        )
        unreadable: list[str] = []
        for entry in expected:
            key = str(entry["key"])
            response = None
            try:
                response = client.get_object(bucket, key)
                payload = response.read()
            except Exception as exc:  # noqa: BLE001 - el SDK lanza excepciones propias
                unreadable.append(f"{key}: {type(exc).__name__}")
                continue
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()
            digest = sha256_bytes(payload)
            if digest != entry["sha256"]:
                unreadable.append(f"{key}: sha256 {digest} != {entry['sha256']}")
        require(
            not unreadable,
            f"{len(unreadable)} objeto(s) no legibles o con contenido distinto: "
            + "; ".join(unreadable[:4]),
        )
        listed = {item.object_name for item in client.list_objects(bucket, recursive=True)}
        extra = sorted(listed - {str(entry["key"]) for entry in expected})
        require(
            not extra,
            f"el bucket tiene {len(extra)} objeto(s) que el backup no contiene: {extra[:4]}",
        )
        return True, f"{len(expected)} objetos leidos por clave con sha256 identico y sin sobrantes"

    return _run("e_objetos", body, required="MinIO")


# --- (f) vectores: puntos, dimensiones y un hit concreto -------------------


def check_vectors(manifest: dict, url: str, api_key: str | None) -> CheckResult:
    def body() -> tuple[bool, str]:
        base_url = qdrant_base_url(url)
        collections = list(manifest["qdrant"].get("collections") or [])
        require(bool(collections), "el manifiesto no declara colecciones de Qdrant")
        details: list[str] = []
        for entry in collections:
            name = str(entry["name"])
            info = collection_info(base_url, api_key, name)
            require(
                int(info["points"]) == int(entry["points"]),
                f"coleccion {name}: {info['points']} puntos restaurados, "
                f"el backup declara {entry['points']}",
            )
            require(
                info["dimensions"] == entry["dimensions"],
                f"coleccion {name}: dimensiones {info['dimensions']} != "
                f"del backup {entry['dimensions']}",
            )
            sample = entry.get("sample_point_id")
            require(
                bool(sample),
                f"el backup no guardo un punto de ejemplo de {name}: no se puede probar "
                "que un hit concreto se recupera",
            )
            hit = _json_request(
                f"{base_url}/collections/{name}/points/{sample}",
                api_key,
                what=f"recuperar punto {sample} de {name}",
            )
            got_id = str(hit["result"].get("id"))
            require(
                got_id == str(sample),
                f"coleccion {name}: el punto de ejemplo devolvio id={got_id}, se esperaba {sample}",
            )
            details.append(f"{name}: {info['points']} pts, dims={info['dimensions']}, hit={got_id}")
        return True, "; ".join(details)

    return _run("f_vectores", body, required="Qdrant")


# --- Orquestacion -----------------------------------------------------------


@dataclass(frozen=True)
class VerifyConfig:
    manifest_path: Path
    pg_target: PsqlTarget
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    qdrant_url: str
    qdrant_api_key: str | None
    app_base_url: str | None
    versions_dir: Path | None


def verify(config: VerifyConfig, *, phase: str = PHASE_ALL) -> tuple[bool, list[CheckResult], dict]:
    """Ejecuta las comprobaciones de una fase y devuelve `(ok, resultados, informe)`.

    `phase=data` compara los datos restaurados contra el manifiesto sin la
    aplicacion; `phase=app` arranca/consulta la app. El orden importa: arrancar
    la app muta la base fuera de produccion (ver `PHASE_DATA`).
    """
    manifest = load_manifest(config.manifest_path)
    backup_dir = config.manifest_path if config.manifest_path.is_dir() else config.manifest_path.parent
    target = PsqlTarget(
        mode=config.pg_target.mode,
        database=str(manifest["postgres"]["database"]),
        user=config.pg_target.user,
        container=config.pg_target.container,
        host=config.pg_target.host,
        port=config.pg_target.port,
        password=config.pg_target.password,
    )

    results: list[CheckResult] = []
    if phase in (PHASE_ALL, PHASE_DATA):
        results.append(check_schema(manifest, backup_dir, target))
        results.append(check_counts(manifest, target))
        results.append(check_alembic(manifest, target, versions_dir=config.versions_dir))
        results.append(
            check_objects(
                manifest, config.minio_endpoint, config.minio_access_key, config.minio_secret_key
            )
        )
        results.append(check_vectors(manifest, config.qdrant_url, config.qdrant_api_key))
    if phase in (PHASE_ALL, PHASE_APP):
        results.append(
            check_app(manifest, config.app_base_url or "")
            if config.app_base_url
            else CheckResult(
                "d_aplicacion",
                False,
                "NO SE PUDO COMPROBAR: falta --app-base-url. Levanta la aplicacion contra "
                "la base restaurada (docker compose up backend, o uvicorn main:app) y "
                "pasa su URL: sin esta comprobacion el restore no esta verificado.",
            )
        )

    ok = all(result.passed for result in results)
    report = {
        "backup_id": manifest["backup_id"],
        "manifest": str(backup_dir / "manifest.json"),
        "alembic_head": manifest["alembic_head"],
        "phase": phase,
        "ok": ok,
        "checks_total": len(results),
        "checks_passed": sum(1 for result in results if result.passed),
        "checks": [result.as_dict() for result in results],
    }
    return ok, results, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verificacion fail-closed de un restore.")
    parser.add_argument("--manifest", required=True, help="Directorio del backup o manifest.json.")
    parser.add_argument("--report-out", default=None, help=f"Ruta del informe (por defecto {REPORT_FILENAME}).")
    parser.add_argument("--pg-user", default="portfolio")
    parser.add_argument("--pg-mode", choices=("auto", "docker", "local"), default="auto")
    parser.add_argument("--pg-container", default=None)
    parser.add_argument("--pg-host", default=None)
    parser.add_argument("--pg-port", type=int, default=None)
    parser.add_argument("--pg-password", default=None)
    parser.add_argument("--minio-endpoint", default="127.0.0.1:9002")
    parser.add_argument("--minio-access-key", default="portfolio")
    parser.add_argument("--minio-secret-key", default="portfoliosecret")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--qdrant-api-key", default=None)
    parser.add_argument(
        "--app-base-url",
        default=None,
        help="URL de la app levantada contra la base restaurada. Sin ella, d_aplicacion FALLA.",
    )
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default=PHASE_ALL,
        help=(
            "data = esquema/conteos/alembic/objetos/vectores, SIN la app; "
            "app = solo el arranque y los endpoints. Los conteos van antes del "
            "arranque porque la app inserta filas si APP_ENV != production"
        ),
    )
    parser.add_argument("--versions-dir", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.versions_dir:
        args.versions_dir = Path(args.versions_dir)
    resolved = args.pg_mode
    if resolved == "auto":
        import shutil

        resolved = "docker" if (args.pg_container or not shutil.which("pg_dump")) else "local"
    config = VerifyConfig(
        manifest_path=Path(args.manifest),
        pg_target=PsqlTarget(
            mode=resolved,
            database="postgres",
            user=args.pg_user,
            container=args.pg_container,
            host=args.pg_host,
            port=args.pg_port,
            password=args.pg_password,
        ),
        minio_endpoint=args.minio_endpoint,
        minio_access_key=args.minio_access_key,
        minio_secret_key=args.minio_secret_key,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        app_base_url=args.app_base_url,
        versions_dir=args.versions_dir,
    )
    try:
        ok, results, report = verify(config, phase=args.phase)
    except FailClosedError as exc:
        print(f"verify_restore: FALLO antes de comprobar: {exc}", file=sys.stderr)
        return 1
    print(format_table(results, heading=f"Verificacion del restore ({args.phase}, fail-closed)"))
    print(f"\n{report['checks_passed']}/{report['checks_total']} comprobaciones superadas")
    suffix = "" if args.phase == PHASE_ALL else f"_{args.phase}"
    default_name = f"verify_report{suffix}.json"
    target_path = Path(args.report_out) if args.report_out else Path(args.manifest) / default_name
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"informe: {target_path}")
    if not ok:
        print(
            "RESULTADO: FALLO. Un restore sin verificar NO es una recuperacion; "
            "repeta el restore o recupera otro backup.",
            file=sys.stderr,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
