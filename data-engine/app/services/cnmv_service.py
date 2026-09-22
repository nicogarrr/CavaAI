"""CNMV OIR (otra informacion relevante) reads — official Spanish regulator.

On-demand per-issuer reads (like insider signals): one conservative GET of
the daily OIR listing, filtered to a REVIEWED issuer mapping. Unmapped
tickers stay unavailable (never guessed). Failures degrade honestly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.services import cnmv_mapping
from app.services.connectors import cnmv
from app.services.provenance import Coverage, SourceKind, provenance


def get_oir_for_ticker(ticker: str, *, days: int = 7) -> dict:
    """OIR filings for a mapped Spanish issuer over the last N days."""
    wanted = ticker.strip().upper()
    issuer = cnmv_mapping.resolve_issuer(wanted)
    if issuer is None:
        return {
            "ticker": wanted,
            "status": "unavailable",
            "reason": "no reviewed CNMV mapping (unknown or ambiguous); never guessed",
            "filings": [],
        }
    try:
        filings = asyncio.run(cnmv.fetch_oir_filings(days=days))
    except cnmv.CNMVParseError as exc:
        return {
            "ticker": wanted,
            "status": "degraded",
            "reason": f"CNMV page structure changed: {exc}",
            "filings": [],
        }
    except Exception as exc:  # noqa: BLE001 — red/HTTP: degradar, nunca 500
        return {
            "ticker": wanted,
            "status": "degraded",
            "reason": f"{type(exc).__name__}: {exc}",
            "filings": [],
        }
    mine = [f for f in filings if f["nif"].replace("-", "") == issuer.nif.replace("-", "")]
    for filing in mine:
        filing["ticker"] = issuer.ticker
    return {
        "ticker": issuer.ticker,
        "status": "ok",
        "legal_name": issuer.legal_name,
        "nif": issuer.nif,
        "isin": issuer.isin,
        "days": days,
        "filings": mine,
        "fetched_at": datetime.now(UTC).isoformat(),
        "provenance": provenance(
            "CNMV",
            SourceKind.OFFICIAL,
            source_url=cnmv.OIR_RESULTS_URL,
            coverage=Coverage.OK if mine else Coverage.UNAVAILABLE,
            note="Regulador oficial ES; lectura bajo demanda (1 GET conservador).",
        ),
    }
