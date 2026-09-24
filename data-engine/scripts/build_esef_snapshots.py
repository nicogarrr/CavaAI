"""Genera snapshots ESEF (xBRL-JSON normalizado) para emisores IBEX reviewed.

Fuente: filings.xbrl.org (indice ESEF de XBRL International, gratuito, sin key).
Para cada LEI con filings ES se toma el filing MAS RECIENTE con json_url y se
normaliza a un layout tipo companyfacts. Solo se construyen snapshots de
emisores cuyo nombre legal resuelve contra la tabla REVIEWED de cnmv_mapping:
ningun ticker se asigna por aproximacion; los no resueltos quedan listados en
el manifest como "unresolved", nunca inventados.

Uso:
    python scripts/build_esef_snapshots.py --out data/esef_snapshots \
        --country ES --fetched-at 2026-09-24

Manifest: {"issuers": {LEI: {ticker, entity_name, period_end, fxo_id, sha256}},
           "unresolved": {LEI: entity_name}, "fetched_at": ..., "source": ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.services.cnmv_mapping import resolve_issuer
from app.services.connectors.esef import (
    EsefClient,
    EsefError,
    EsefFiling,
    normalize_xbrl_json,
)

SOURCE = "filings.xbrl.org (XBRL International ESEF filing index), xBRL-JSON render"


def latest_filing_per_lei(filings: list[EsefFiling]) -> dict[str, EsefFiling]:
    """Un filing por LEI: el de period_end mas reciente que tenga json_url."""
    best: dict[str, EsefFiling] = {}
    for f in sorted(filings, key=lambda x: x.period_end or ""):
        if not f.json_url:
            continue
        best[f.lei] = f  # sorted ascending: last write wins = latest period
    return best


async def build(out: Path, country: str, fetched_at: str, client: EsefClient) -> dict:
    filings = await client.list_all_filings(country)
    latest = latest_filing_per_lei(filings)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)

    issuers: dict[str, dict] = {}
    unresolved: dict[str, str] = {}
    for lei, filing in sorted(latest.items()):
        try:
            name = await client.get_entity_name(lei)
        except EsefError:
            name = ""
        issuer = resolve_issuer(name) if name else None
        if issuer is None:
            unresolved[lei] = name or "<entity lookup failed>"
            continue
        doc = await client.fetch_filing_json(filing)
        facts = normalize_xbrl_json(doc)
        payload = {
            "lei": lei,
            "ticker": issuer.ticker,
            "entity_name": name,
            "period_end": filing.period_end,
            "fxo_id": filing.fxo_id,
            "sha256": filing.sha256,
            "fetched_at": fetched_at,
            "facts": facts,
        }
        path = out / "snapshots" / f"{lei}.json"
        path.write_text(json.dumps(payload))
        issuers[lei] = {
            "ticker": issuer.ticker,
            "entity_name": name,
            "period_end": filing.period_end,
            "fxo_id": filing.fxo_id,
            "sha256": filing.sha256,
        }
        n = sum(len(u) for c in facts.values() for u in c.values())
        print(f"{issuer.ticker} ({name}): {len(facts)} conceptos, {n} entradas, period {filing.period_end} -> {path}")

    manifest = {
        "issuers": dict(sorted(issuers.items())),
        "unresolved": dict(sorted(unresolved.items())),
        "fetched_at": fetched_at,
        "source": SOURCE,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"manifest -> {out / 'manifest.json'} ({len(issuers)} issuers, {len(unresolved)} unresolved)")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--country", default="ES")
    parser.add_argument("--fetched-at", required=True, help="Fecha de captura (provenance).")
    args = parser.parse_args()
    asyncio.run(build(Path(args.out), args.country, args.fetched_at, EsefClient()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
