"""Reviewed ticker -> CNMV issuer mapping (Spanish listed equities).

Parent constraint: no company-name-to-NIF guessing. Entries are reviewed
manually against CNMV registry pages (normalized legal name + NIF + ISIN +
ticker aliases). Unknown, ambiguous or conflicting mappings resolve to None
(unavailable) — attribution is never guessed.

Reviewed 2026-09-22 against CNMV entity/ISIN information pages.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CNMVIssuer:
    ticker: str
    legal_name: str          # normalized CNMV legal name (uppercase)
    nif: str
    isin: str
    aliases: tuple[str, ...] = ()


# Reviewed seed table (IBEX heavyweights). Extend only after verifying each
# entry against the CNMV registry; never auto-generate rows.
REVIEWED_ISSUERS: tuple[CNMVIssuer, ...] = (
    CNMVIssuer("SAN", "BANCO SANTANDER, S.A.", "A-39000013", "ES0113900J37", ("SANTANDER", "SAN.MC")),
    CNMVIssuer("ITX", "INDUSTRIA DE DISEÑO TEXTIL, S.A.", "A-15075062", "ES0148396007", ("INDITEX", "ITX.MC")),
    CNMVIssuer("IBE", "IBERDROLA, S.A.", "A-48010611", "ES0144580Y14", ("IBERDROLA", "IBE.MC")),
    CNMVIssuer("BBVA", "BANCO BILBAO VIZCAYA ARGENTARIA, S.A.", "A-48265169", "ES0113211835", ("BBVA", "BBVA.MC")),
    CNMVIssuer("TEF", "TELEFONICA, S.A.", "A-28015865", "ES0178430E18", ("TELEFONICA", "TEF.MC")),
    CNMVIssuer("REP", "REPSOL, S.A.", "A-78374725", "ES0173516115", ("REPSOL", "REP.MC")),
)


def _normalize(name: str) -> str:
    return " ".join(name.upper().replace(",", " ").split())


def resolve_issuer(query: str) -> CNMVIssuer | None:
    """Resolve a ticker/ISIN/NIF/exact legal name to a reviewed issuer.

    Returns None when the query matches nothing or matches ambiguously:
    unresolved or conflicting mappings stay unavailable, never guessed.
    Partial/free-text matches are intentionally NOT attempted.
    """
    q = _normalize(query)
    if not q:
        return None
    matches = []
    for issuer in REVIEWED_ISSUERS:
        keys = {issuer.ticker.upper(), issuer.isin.upper(), issuer.nif.upper().replace("-", "")}
        keys |= {_normalize(a) for a in issuer.aliases}
        keys.add(_normalize(issuer.legal_name))
        if q in keys or q.replace("-", "") == issuer.nif.upper().replace("-", ""):
            matches.append(issuer)
    return matches[0] if len(matches) == 1 else None


def issuer_for_nif(nif: str) -> CNMVIssuer | None:
    """Reverse lookup used when attributing CNMV filings to portfolio tickers."""
    normalized = nif.upper().replace("-", "")
    matches = [i for i in REVIEWED_ISSUERS if i.nif.upper().replace("-", "") == normalized]
    return matches[0] if len(matches) == 1 else None
