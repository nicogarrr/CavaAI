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
    # Tanda 2 (2026-09-25): mismo metodo que la tanda 1 (datosentidad +
    # ancv/isin de CNMV). Cuando el FISN no da nemotecnico corto, el ticker
    # se confirma con ficha BME/bsmarkets (LDA, LRE). MEDIASET ESPAÑA se
    # excluye: sin ISIN equity en CNMV tras su absorcion por MFE - hueco
    # honesto, como FERROVIAL.
    CNMVIssuer("FCC", "FOMENTO DE CONSTRUCCIONES Y CONTRATAS, S.A.", "A-28037224", "ES0122060314", ("FCC", "FCC.MC", "FOMENTO DE CONSTRUCCIONES Y CONTRATAS SA")),
    CNMVIssuer("COL", "COLONIAL SFL, SOCIMI, S.A.", "A-28027399", "ES0139140174", ("COLONIAL", "COL.MC", "INMOBILIARIA COLONIAL SOCIMI SA", "INMOBILIARIA COLONIAL SOCIMI SOCIEDAD ANONIMA")),
    CNMVIssuer("A3M", "ATRESMEDIA CORPORACION DE MEDIOS DE COMUNICACION, S.A.", "A-78839271", "ES0109427734", ("ATRESMEDIA", "A3M.MC", "ATRESMEDIA CORPORACION DE MEDIOS DE COMUNICACION SA")),
    CNMVIssuer("LOG", "LOGISTA INTEGRAL, S.A.", "A-87008579", "ES0105027009", ("LOGISTA", "LOG.MC", "LOGISTA INTEGRAL SA")),
    CNMVIssuer("VID", "VIDRALA, S.A.", "A-01004324", "ES0183746314", ("VIDRALA", "VID.MC", "VIDRALA SA")),
    CNMVIssuer("CIE", "CIE AUTOMOTIVE, S.A.", "A-20014452", "ES0105630315", ("CIE", "CIE.MC", "CIE AUTOMOTIVE SA")),
    CNMVIssuer("ACX", "ACERINOX, S.A.", "A-28250777", "ES0132105018", ("ACERINOX", "ACX.MC", "ACERINOX SA")),
    CNMVIssuer("FDR", "FLUIDRA, S.A.", "A-17728593", "ES0137650018", ("FLUIDRA", "FDR.MC", "FLUIDRA SA")),
    CNMVIssuer("ALM", "ALMIRALL, S.A.", "A-58869389", "ES0157097017", ("ALMIRALL", "ALM.MC", "ALMIRALL SA")),
    CNMVIssuer("ENC", "ENCE ENERGIA Y CELULOSA, S.A.", "A-28212264", "ES0130625512", ("ENCE", "ENC.MC", "ENCE ENERGIA Y CELULOSA SA")),
    CNMVIssuer("TLGO", "TALGO, S.A.", "A-84453075", "ES0105065009", ("TALGO", "TLGO.MC", "TALGO SA")),
    CNMVIssuer("ROVI", "LABORATORIOS FARMACEUTICOS ROVI, S.A.", "A-28041283", "ES0157261019", ("ROVI", "ROVI.MC", "LABORATORIOS FARMACEUTICOS ROVI SA")),
    CNMVIssuer("OLE", "DEOLEO, S.A.", "A-48012009", "ES0110047919", ("DEOLEO", "OLE.MC", "DEOLEO SA")),
    CNMVIssuer("CAF", "CONSTRUCCIONES Y AUXILIAR DE FERROCARRILES, S.A.", "A-20001020", "ES0121975009", ("CAF", "CAF.MC", "CONSTRUCCIONES Y AUXILIAR DE FERROCARRILES SA")),
    CNMVIssuer("OHL", "OBRASCON HUARTE LAIN, S.A.", "A-48010573", "ES0142090317", ("OHLA", "OHL.MC", "OBRASCON HUARTE LAIN SA")),
    CNMVIssuer("GEST", "GESTAMP AUTOMOCION, S.A.", "A-48943864", "ES0105223004", ("GESTAMP", "GEST.MC", "GESTAMP AUTOMOCION SA")),
    CNMVIssuer("ENO", "ELECNOR, S.A.", "A-48027056", "ES0129743318", ("ELECNOR", "ENO.MC", "ELECNOR SA")),
    CNMVIssuer("GCO", "GRUPO CATALANA OCCIDENTE, S.A.", "A-08168064", "ES0116920333", ("CATALANA OCCIDENTE", "GCO.MC", "GRUPO CATALANA OCCIDENTE SA")),
    CNMVIssuer("LDA", "LINEA DIRECTA ASEGURADORA, S.A., COMPAÑIA DE SEGUROS Y REASEGUROS", "A-80871031", "ES0105546008", ("LINEA DIRECTA", "LDA.MC", "LINEA DIRECTA ASEGURADORA SOCIEDAD ANONIMA COMPAÑIA DE SEGUROS Y REASEGUROS")),
    CNMVIssuer("CASH", "PROSEGUR CASH, S.A.", "A-87498564", "ES0105229001", ("PROSEGUR CASH", "CASH.MC", "PROSEGUR CASH SA")),
    CNMVIssuer("LRE", "LAR ESPAÑA REAL ESTATE SOCIMI, S.A.", "A-86918307", "ES0105015012", ("LAR ESPAÑA", "LRE.MC", "LAR ESPAÑA REAL ESTATE SOCIMI SA")),
    CNMVIssuer("TUB", "TUBACEX, S.A.", "A-01003946", "ES0132945017", ("TUBACEX", "TUB.MC", "TUBACEX SA")),
    CNMVIssuer("ALNT", "ALANTRA PARTNERS, S.A.", "A-81862724", "ES0126501131", ("ALANTRA", "ALNT.MC", "ALANTRA PARTNERS SA")),
    CNMVIssuer("AZK", "AZKOYEN, S.A.", "A-31065618", "ES0112458312", ("AZKOYEN", "AZK.MC", "AZKOYEN SA")),
    # Tanda 3 (2026-09-25): mismo metodo CNMV. RED confirmado con Yahoo
    # (RED.MC) porque el FISN no da codigo corto. EDREAMS ODIGEO excluida:
    # sin ISIN equity en CNMV (A02850956) - hueco honesto documentado.
    CNMVIssuer("RED", "REDEIA CORPORACION, S.A.", "A-78003662", "ES0173093024", ("REDEIA", "RED.MC", "RED ELECTRICA", "REDEIA CORPORACION SA")),
    CNMVIssuer("HOME", "NEINOR HOMES, S.A.", "A-95786562", "ES0105251005", ("NEINOR", "HOME.MC", "NEINOR HOMES SA")),
    CNMVIssuer("FAE", "FAES FARMA, S.A.", "A-48004360", "ES0134950F36", ("FAES", "FAE.MC", "FAES FARMA SA")),
    CNMVIssuer("MEL", "MELIA HOTELS INTERNATIONAL S.A.", "A-78304516", "ES0176252718", ("MELIA", "MEL.MC", "MELIA HOTELS", "MELIA HOTELS INTERNATIONAL SA")),
    CNMVIssuer("EBRO", "EBRO FOODS, S.A.", "A-47412333", "ES0112501012", ("EBRO", "EBRO.MC", "EBRO FOODS SA")),
    CNMVIssuer("SCYR", "SACYR, S.A.", "A-28013811", "ES0182870214", ("SACYR", "SCYR.MC", "SACYR SA")),
    CNMVIssuer("SLR", "SOLARIA ENERGIA Y MEDIOAMBIENTE, S.A.", "A-83511501", "ES0165386014", ("SOLARIA", "SLR.MC", "SOLARIA ENERGIA Y MEDIO AMBIENTE SA")),
    CNMVIssuer("ECR", "ERCROS, S.A.", "A-08000630", "ES0125140A14", ("ERCROS", "ECR.MC", "ERCROS SA")),
    CNMVIssuer("IBG", "IBERPAPEL GESTION, S.A.", "A-21248893", "ES0147561015", ("IBERPAPEL", "IBG.MC", "IBERPAPEL GESTION SA")),
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
