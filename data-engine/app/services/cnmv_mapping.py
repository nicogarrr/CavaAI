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
# Aliases ending in "SA"/"SOCIEDAD ANONIMA" are the ESEF legal-name forms,
# verified 2026-09-24 against filings.xbrl.org (each matched exactly one LEI).
REVIEWED_ISSUERS: tuple[CNMVIssuer, ...] = (
    CNMVIssuer("SAN", "BANCO SANTANDER, S.A.", "A-39000013", "ES0113900J37", ("SANTANDER", "SAN.MC")),
    CNMVIssuer("ITX", "INDUSTRIA DE DISEÑO TEXTIL, S.A.", "A-15075062", "ES0148396007", ("INDITEX", "ITX.MC")),
    CNMVIssuer("IBE", "IBERDROLA, S.A.", "A-48010611", "ES0144580Y14", ("IBERDROLA", "IBE.MC", "IBERDROLA SA")),
    CNMVIssuer("BBVA", "BANCO BILBAO VIZCAYA ARGENTARIA, S.A.", "A-48265169", "ES0113211835", ("BBVA", "BBVA.MC", "BANCO BILBAO VIZCAYA ARGENTARIA SOCIEDAD ANONIMA")),
    CNMVIssuer("TEF", "TELEFONICA, S.A.", "A-28015865", "ES0178430E18", ("TELEFONICA", "TEF.MC", "TELEFONICA SA")),
    CNMVIssuer("REP", "REPSOL, S.A.", "A-78374725", "ES0173516115", ("REPSOL", "REP.MC", "REPSOL SA")),
    # Tanda 1 (2026-09-25): verificada fila a fila contra paginas oficiales
    # CNMV - datosentidad (nombre legal + NIF) y ancv/isin (ISIN de acciones
    # CFI ESVU** y nemotecnico oficial del FISN). FERROVIAL se excluye a
    # proposito: la cotizada actual es FERROVIAL N.V. (entidad neerlandesa,
    # N0119863I) y el ESEF del manifest corresponde a la S.A. extinguida -
    # conflicto de entidad, se deja sin resolver.
    CNMVIssuer("TRE", "TECNICAS REUNIDAS, S.A.", "A-28092583", "ES0178165017", ("TECNICAS REUNIDAS", "TRE.MC", "TECNICAS REUNIDAS SA")),
    CNMVIssuer("CLNX", "CELLNEX TELECOM, S.A.", "A-64907306", "ES0105066007", ("CELLNEX", "CLNX.MC", "CELLNEX TELECOM SA")),
    CNMVIssuer("ELE", "ENDESA, S.A.", "A-28023430", "ES0130670112", ("ENDESA", "ELE.MC", "ENDESA SA")),
    CNMVIssuer("CABK", "CAIXABANK, S.A.", "A-08663619", "ES0140609019", ("CAIXABANK", "CABK.MC", "CAIXABANK SA")),
    CNMVIssuer("ENG", "ENAGAS, S.A.", "A-28294726", "ES0130960018", ("ENAGAS", "ENG.MC", "ENAGAS SA")),
    CNMVIssuer("ACS", "ACS, ACTIVIDADES DE CONSTRUCCION Y SERVICIOS, S.A.", "A-28004885", "ES0167050915", ("ACS", "ACS.MC", "ACS ACTIVIDADES DE CONSTRUCCION Y SERVICIOS SA")),
    CNMVIssuer("MAP", "MAPFRE, S.A.", "A-08055741", "ES0124244E34", ("MAPFRE", "MAP.MC", "MAPFRE SA")),
    CNMVIssuer("AMS", "AMADEUS IT GROUP, S.A.", "A-84236934", "ES0109067019", ("AMADEUS", "AMS.MC", "AMADEUS IT GROUP SOCIEDAD ANONIMA", "AMADEUS IT GROUP SA")),
    CNMVIssuer("ANA", "ACCIONA, S.A.", "A-08001851", "ES0125220311", ("ACCIONA", "ANA.MC", "ACCIONA SA")),
    CNMVIssuer("ANE", "CORPORACION ACCIONA ENERGIAS RENOVABLES, S.A.", "A-85483311", "ES0105563003", ("ACCIONA ENERGIA", "ANE.MC", "CORPORACION ACCIONA ENERGIAS RENOVABLES SA")),
    CNMVIssuer("PSG", "PROSEGUR, COMPAÑIA DE SEGURIDAD, S.A.", "A-28430882", "ES0175438003", ("PROSEGUR", "PSG.MC", "PROSEGUR COMPAÑIA DE SEGURIDAD SA")),
    CNMVIssuer("IDR", "INDRA SISTEMAS, S.A.", "A-28599033", "ES0118594417", ("INDRA", "IDR.MC", "INDRA SISTEMAS SA")),
    CNMVIssuer("VIS", "VISCOFAN, S.A.", "A-31065501", "ES0184262212", ("VISCOFAN", "VIS.MC", "VISCOFAN SA")),
    CNMVIssuer("AENA", "AENA, S.M.E., S.A.", "A-86212420", "ES0105046017", ("AENA", "AENA.MC", "AENA SME SA", "AENA S.M.E. SA")),
    CNMVIssuer("BKT", "BANKINTER, S.A.", "A-28157360", "ES0113679I37", ("BANKINTER", "BKT.MC", "BANKINTER SOCIEDAD ANONIMA", "BANKINTER SA")),
    CNMVIssuer("SAB", "BANCO DE SABADELL, S.A.", "A-08000143", "ES0113860A34", ("SABADELL", "SAB.MC", "BANCO SABADELL", "BANCO DE SABADELL SA")),
    CNMVIssuer("NTGY", "NATURGY ENERGY GROUP, S.A.", "A-08015497", "ES0116870314", ("NATURGY", "NTGY.MC", "NATURGY ENERGY GROUP SA")),
    CNMVIssuer("MRL", "MERLIN PROPERTIES, SOCIMI, S.A.", "A-86977790", "ES0105025003", ("MERLIN", "MRL.MC", "MERLIN PROPERTIES SOCIMI SA")),
    # GRF usa la clase A con voto (ES0171996087); la clase B sin voto
    # (ES0171996095) queda como alias, no como ISIN principal.
    CNMVIssuer("GRF", "GRIFOLS, S.A.", "A-58389123", "ES0171996087", ("GRIFOLS", "GRF.MC", "GRIFOLS SA")),
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
