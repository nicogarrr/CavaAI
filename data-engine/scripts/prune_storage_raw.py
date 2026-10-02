#!/usr/bin/env python3
"""Poda de ``storage/raw/`` por antiguedad y por presupuesto (stdlib only).

Por que existe: ``storage/raw/`` es la cache de ingesta de filings SEC/ESEF.
No esta versionada (``.gitignore``: ``/storage/`` y ``data-engine/storage/raw/``),
asi que no es un problema de repositorio: es un problema de disco. Crece sin
tope con cada ingesta y el sintoma (un ``du`` de varios GB y una maquina sin
espacio) aparece cuando ya duele.

Por que ``--dry-run`` es el DEFECTO y no una opcion: una poda destructiva
ejecutada por error borra material que se re--descarga de SEC a un coste alto
por GB. Sin ``--apply`` este script no toca el disco. always.

Presupuesto declarado (lo que se considera aceptable en una maquina de desarrollo):
    MAX_AGE_DAYS  = 90   material de ingesta mas viejo que esto se puede re-bajar
    MAX_TOTAL_GB  = 5.0  tope total de ``storage/raw/``

Uso:
    python scripts/prune_storage_raw.py                 # dry-run, solo informa
    python scripts/prune_storage_raw.py --max-age-days 30
    python scripts/prune_storage_raw.py --apply         # DESTRUCTIVO
    python scripts/prune_storage_raw.py --json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Candidatos: la cache vive bajo ``data-engine/storage/raw`` y, en algunos
# montajes, en ``<repo>/storage/raw``. Se comprueban los dos.
CANDIDATES = [
    ROOT / "storage" / "raw",
    ROOT.parent / "storage" / "raw",
]

DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MAX_TOTAL_GB = 5.0


@dataclass
class Entry:
    path: Path
    bytes: int
    mtime: float

    @property
    def age_days(self) -> float:
        return (time.time() - self.mtime) / 86400.0


def dir_size(path: Path) -> tuple[int, float]:
    """Bytes y mtime mas reciente del arbol. mtime: lo podable es lo recien."""
    total = 0
    newest = 0.0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                st = f.stat()
            except OSError:
                continue
            total += st.st_size
            newest = max(newest, st.st_mtime)
    return total, newest


def collect(root: Path) -> list[Entry]:
    out: list[Entry] = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        size, newest = dir_size(child)
        out.append(Entry(path=child, bytes=size, mtime=newest))
    return out


def human(n: float) -> str:
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def existing_roots() -> list[Path]:
    return [p for p in CANDIDATES if p.is_dir()]


def plan(entries: list[Entry], max_age_days: float, max_total_gb: float) -> dict:
    """Que se borraria, separando las dos reglas para poder explicarlas."""
    now = time.time()
    cutoff = now - max_age_days * 86400
    total = sum(e.bytes for e in entries)

    by_age = [e for e in entries if e.mtime < cutoff]
    # El presupuesto se aplica DESPUES de la antiguedad, sobre lo que queda, y
    # empieza por lo mas viejo: es lo que mas probable es que sobre.
    remaining = [e for e in entries if e.mtime >= cutoff]
    remaining.sort(key=lambda e: e.mtime)
    budget_bytes = max_total_gb * 1024**3

    by_budget: list[Entry] = []
    running = sum(e.bytes for e in remaining)
    while remaining and running > budget_bytes:
        victim = remaining.pop(0)
        by_budget.append(victim)
        running -= victim.bytes

    keep = {e.path for e in remaining}
    prune = {e.path for e in by_age} | {e.path for e in by_budget}

    return {
        "total_bytes": total,
        "total_human": human(total),
        "entries": len(entries),
        "prune_count": len(prune),
        "prune_bytes": sum(e.bytes for e in entries if e.path in prune),
        "keep_count": len(keep),
        "over_budget": total > budget_bytes,
        "by_age": sorted(by_age, key=lambda e: e.mtime),
        "by_budget": by_budget,
        "keep": sorted(remaining, key=lambda e: e.mtime),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Poda de storage/raw (dry-run por defecto).")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="EJECUTA el borrado. Sin este flag no se toca el disco.",
    )
    ap.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS)
    ap.add_argument("--max-total-gb", type=float, default=DEFAULT_MAX_TOTAL_GB)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Raiz de storage/raw a podar (para probar contra datos de mentira).",
    )
    args = ap.parse_args()

    roots = [args.root] if args.root else existing_roots()
    if not roots:
        msg = "no existe storage/raw (ni data-engine/storage/raw ni <repo>/storage/raw)"
        print(msg if not args.json else json.dumps({"skipped": msg}))
        return 0

    all_plans = []
    for root in roots:
        entries = collect(root)
        p = plan(entries, args.max_age_days, args.max_total_gb)
        p["root"] = str(root)
        all_plans.append(p)

        if args.apply:
            for e in p["by_age"] + p["by_budget"]:
                shutil.rmtree(e.path, ignore_errors=False)

    if args.json:
        print(
            json.dumps(
                {
                    "applied": args.apply,
                    "max_age_days": args.max_age_days,
                    "max_total_gb": args.max_total_gb,
                    "roots": [
                        {
                            "root": p["root"],
                            "total_bytes": p["total_bytes"],
                            "entries": p["entries"],
                            "prune_count": p["prune_count"],
                            "prune_bytes": p["prune_bytes"],
                            "keep_count": p["keep_count"],
                            "over_budget": p["over_budget"],
                            "prune": [
                                {"path": str(e.path), "bytes": e.bytes, "age_days": round(e.age_days, 1)}
                                for e in p["by_age"] + p["by_budget"]
                            ],
                        }
                        for p in all_plans
                    ],
                },
                indent=2,
            )
        )
        return 0

    for p in all_plans:
        print(f"{p['root']}")
        print(
            f"  {p['entries']} entradas, {p['total_human']}"
            f"  (presupuesto {args.max_total_gb} GB)"
            + ("  <- POR ENCIMA DEL PRESUPUESTO" if p["over_budget"] else "")
        )
        if p["by_age"]:
            print(f"  por antiguedad (> {args.max_age_days:g} d): {len(p['by_age'])}")
            for e in p["by_age"][:10]:
                print(f"    {e.age_days:8.1f} d  {human(e.bytes):>9}  {e.path.name}")
            if len(p["by_age"]) > 10:
                print(f"    ... y {len(p['by_age']) - 10} mas")
        if p["by_budget"]:
            print(f"  por presupuesto: {len(p['by_budget'])}")
            for e in p["by_budget"][:10]:
                print(f"    {e.age_days:8.1f} d  {human(e.bytes):>9}  {e.path.name}")
        print(
            f"  SE BORRARIAN: {p['prune_count']} entradas, {human(p['prune_bytes'])}"
            f"   |   se conservan: {p['keep_count']}"
        )
    if not args.apply:
        print("\nDRY-RUN: no se ha borrado nada. Reejecuta con --apply para hacerlo.")
    else:
        print("\nAPLICADO: borrado ejecutado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())