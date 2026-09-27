"""Repara un concepto concreto en los snapshots SEC desde el parquet espejo.

Motivacion (B19): build_sec_snapshots truncaba ``val`` con int(), destruyendo
decimales de BPA (7,26 -> 7). En vez de regenerar 2.012 snapshots completos
desde un parquet mas reciente (mezclaria restatements ajenos al fix), este
script reescribe SOLO las entradas del concepto indicado en cada fichero,
preservando decimales via ``_entry_value``.

Uso:
    python scripts/patch_sec_snapshot_concept.py --parquet /tmp/Facts_UsGaap.parquet \
        --snapshots-dir data/sec_snapshots [--concept EarningsPerShareDiluted]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl  # noqa: E402
from sec_snapshot_values import entry_value  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--snapshots-dir", required=True)
    parser.add_argument("--concept", default="EarningsPerShareDiluted")
    args = parser.parse_args()

    snapshots = Path(args.snapshots_dir)
    manifest = json.loads((snapshots / "manifest.json").read_text())
    ciks = [str(cik).zfill(10) for cik in manifest["tickers"].values()]

    df = pl.scan_parquet(args.parquet).filter(
        pl.col("item") == args.concept,
        pl.col("source_folder").str.extract(r"CIK(\d{10})").is_in(ciks),
    ).select("end", "fy", "fp", "form", "filed", "unit_type", "val_dec", "source_folder").collect(engine="streaming")

    by_cik: dict[str, dict] = {}
    for row in df.iter_rows(named=True):
        cik = row["source_folder"].split("_")[0].replace("CIK", "").zfill(10)
        concept = by_cik.setdefault(cik, {"units": {}})
        unit = row["unit_type"] or "USD"
        concept["units"].setdefault(unit, []).append({
            "end": row["end"], "fy": int(row["fy"]) if row["fy"] else None,
            "fp": row["fp"], "form": row["form"], "filed": row["filed"],
            "val": entry_value(row["val_dec"]),
        })

    stats = {"files": 0, "entries": 0, "fractional": 0, "missing": 0}
    for cik, concept in by_cik.items():
        path = snapshots / "companyfacts" / f"CIK{cik}.json"
        if not path.exists():
            stats["missing"] += 1
            continue
        payload = json.loads(path.read_text())
        payload["facts"]["us-gaap"][args.concept] = concept
        path.write_text(json.dumps(payload))  # mismo formato que build_sec_snapshots (sin indent)
        stats["files"] += 1
        for entries in concept["units"].values():
            stats["entries"] += len(entries)
            stats["fractional"] += sum(1 for e in entries if isinstance(e["val"], float))

    print("RESULTADO_PATCH:", json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
