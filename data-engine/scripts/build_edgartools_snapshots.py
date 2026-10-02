"""Construye el snapshot edgartools desde un snapshot SEC existente (offline).

La SEC bloquea las IPs de datacenter (403 permanente en OCI): el snapshot se
genera donde la SEC responde (o desde el mirror HF) y viaja con la app.
Este script NO toca la red: copia ``companyfacts/`` y ``submissions/`` desde
``--sec-snapshot-dir`` (layout de ``build_sec_snapshots.py``) al layout
edgartools y escribe ``manifest.json`` con ``tickers`` + ``synced_at``
(procedencia declarada, nunca implicita).

Uso:
    python scripts/build_edgartools_snapshots.py --sec-snapshot-dir data/sec_snapshots \\
        --out data/edgartools_snapshots --synced-at 2026-09-30T12:00:00+00:00 \\
        TSTEDG:0001234567

Los XML de filings (Form 4 crudo, information table 13F) se colocan a mano en
``filings/<ACCESSION_SIN_GUIONES>/<fichero>.xml`` tras descargarlos donde la
SEC responda; el manifest no los declara uno a uno (el indice del filing ya
acredita cada documento: ver ``sec_filing_evidence``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-snapshot-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--synced-at", required=True, help="ISO-8601 de la fuente (provenance).")
    parser.add_argument("--edgartools", default="5.59.1", help="Pin de edgartools que leera el snapshot.")
    parser.add_argument("targets", nargs="+", help="TICKER:CIK (cik a 10 o sin padding)")
    args = parser.parse_args()

    src = Path(args.sec_snapshot_dir)
    out = Path(args.out)
    (out / "companyfacts").mkdir(parents=True, exist_ok=True)
    (out / "submissions").mkdir(parents=True, exist_ok=True)
    (out / "filings").mkdir(parents=True, exist_ok=True)

    targets: dict[str, str] = {}
    for raw in args.targets:
        ticker, cik = raw.split(":")
        targets[ticker.strip().upper()] = cik.strip().zfill(10)

    src_manifest: dict = {}
    src_manifest_path = src / "manifest.json"
    if src_manifest_path.exists():
        try:
            src_manifest = json.loads(src_manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            src_manifest = {}

    copied = 0
    for ticker, cik in targets.items():
        for kind in ("companyfacts", "submissions"):
            origin = src / kind / f"CIK{cik}.json"
            if kind == "companyfacts" and not origin.exists():
                # build_sec_snapshots.py solo escribe companyfacts/: submissions
                # puede no existir para emisores viejos; no es error.
                continue
            if not origin.exists():
                print(f"aviso: sin {kind} para {ticker} ({origin})", file=sys.stderr)
                continue
            dest = out / kind / f"CIK{cik}.json"
            shutil.copyfile(origin, dest)
            copied += 1
            print(f"{ticker}: {kind} -> {dest}")

    manifest_path = out / "manifest.json"
    existing: dict[str, str] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8")).get("tickers", {})
        except ValueError:
            existing = {}
    existing.update(targets)
    manifest = {
        "tickers": dict(sorted(existing.items())),
        "synced_at": args.synced_at,
        "source": src_manifest.get("source", "SEC EDGAR companyfacts/submissions (formato oficial)"),
        "builder": "scripts/build_edgartools_snapshots.py (copia offline desde snapshot SEC)",
        "edgartools": args.edgartools,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"copiados {copied} ficheros; manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
